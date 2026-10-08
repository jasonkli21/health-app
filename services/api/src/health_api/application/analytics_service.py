"""Stable route-facing analytics operations."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from health_api.application.analytics_artifacts import (
    _artifact_aggregate,
    _persist_signal,
    _signal_scope,
    _snapshot,
    change_insight_state,
    change_recommendation_state,
    create_coverage_recommendation_from_signal,
    create_experiment,
    create_insight_from_signal,
    experiment_result,
    expire_artifact_for_response,
    invalidate_analytics,
    list_artifacts,
    transition_experiment,
    update_experiment,
)
from health_api.application.analytics_computation import (
    _series_from_snapshot,
    _standard_points,
    _tracker_metric_label,
    _tracker_metric_parts,
)
from health_api.application.analytics_contracts import (
    AnalyticsConflict,
    AnalyticsNotFound,
    AnalyticsValidationError,
    ArtifactAggregate,
    MetricSeries,
    StoredSignal,
    _sha256,
)
from health_api.application.analytics_sources import (
    _load_inputs,
    _series,
    list_metric_definitions,
    load_analytics_snapshot,
    metric_definition,
)
from health_api.domain.analytics import (
    ASSOCIATION_PAIRS,
    MAX_ANALYSIS_DAYS,
    AssociationPair,
    AssociationResult,
    EvidenceReference,
    TrendResult,
    build_association_result,
    build_trend_result,
)
from health_api.domain.daily import local_day_bounds
from health_api.persistence.models import HealthObject, PlanningResource
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

__all__ = [
    "AnalyticsConflict",
    "AnalyticsNotFound",
    "AnalyticsValidationError",
    "ArtifactAggregate",
    "StoredSignal",
    "_artifact_aggregate",
    "_load_inputs",
    "_snapshot",
    "_standard_points",
    "_tracker_metric_label",
    "change_insight_state",
    "change_recommendation_state",
    "compute_ai_trend_preview",
    "compute_associations",
    "compute_trend",
    "create_experiment",
    "experiment_result",
    "expire_artifact_for_response",
    "generate_insights",
    "invalidate_analytics",
    "list_artifacts",
    "list_metric_definitions",
    "transition_experiment",
    "update_experiment",
]


def compute_trend(
    session: Session,
    owner_id: UUID,
    metric: str,
    from_date: date,
    to_date: date,
    timezone: str,
    *,
    ai_permitted_only: bool = False,
    prepared_series: MetricSeries | None = None,
) -> StoredSignal:
    if prepared_series is None:
        definition, points, refs, generation = _series(
            session,
            owner_id,
            metric,
            from_date,
            to_date,
            timezone,
            ai_permitted_only=ai_permitted_only,
        )
    else:
        definition, points, refs, generation = prepared_series
    result = build_trend_result(
        metric,
        points,
        definition=definition,
        from_date=from_date,
        to_date=to_date,
        timezone=timezone,
        evidence_refs=refs,
    )
    scope_key = _signal_scope(metric, from_date, to_date, timezone)
    fingerprint = _sha256(
        {
            "method": result.method_version,
            "points": [point.model_dump(mode="json") for point in points],
            "evidence": [ref.model_dump(mode="json") for ref in refs],
        }
    )
    payload = {
        "signal_kind": "trend",
        "metric": metric,
        "title": definition.label,
        "result": result.model_dump(mode="json"),
    }
    start_at = local_day_bounds(from_date, timezone)[0]
    end_at = local_day_bounds(to_date + timedelta(days=1), timezone)[0]
    session.commit()
    obj, artifact = _persist_signal(
        session,
        owner_id,
        scope_key=scope_key,
        input_fingerprint=fingerprint,
        payload=payload,
        evidence_refs=refs,
        valid_from=start_at,
        valid_to=end_at,
        expected_generation=generation,
    )
    return StoredSignal(obj, artifact, result, generation)


def compute_ai_trend_preview(
    session: Session,
    owner_id: UUID,
    metric: str,
    from_date: date,
    to_date: date,
    timezone: str,
    *,
    excluded_object_ids: set[UUID] | None = None,
    as_of: datetime | None = None,
) -> TrendResult | None:
    """Compute one preview from explicitly AI-permitted daily inputs only."""
    tracker_parts = _tracker_metric_parts(metric)
    if tracker_parts is not None:
        tracker_id, _, _ = tracker_parts
        if excluded_object_ids and tracker_id in excluded_object_ids:
            return None
        tracker = session.execute(
            select(HealthObject, PlanningResource)
            .join(
                PlanningResource,
                and_(
                    PlanningResource.owner_id == HealthObject.owner_id,
                    PlanningResource.object_id == HealthObject.id,
                ),
            )
            .where(
                HealthObject.owner_id == owner_id,
                HealthObject.id == tracker_id,
                HealthObject.object_type == "tracker_definition",
                HealthObject.status == "active",
                HealthObject.ai_use_allowed.is_(True),
                PlanningResource.resource_kind == "tracker_definition",
                PlanningResource.lifecycle == "active",
                *(
                    (
                        or_(HealthObject.valid_from.is_(None), HealthObject.valid_from <= as_of),
                        or_(HealthObject.valid_to.is_(None), HealthObject.valid_to > as_of),
                    )
                    if as_of is not None
                    else ()
                ),
            )
        ).one_or_none()
        if tracker is None:
            raise AnalyticsValidationError(
                "The tracker definition must be active and explicitly AI-permitted."
            )
    definition, points, refs, _ = _series(
        session,
        owner_id,
        metric,
        from_date,
        to_date,
        timezone,
        ai_permitted_only=True,
        excluded_object_ids=excluded_object_ids,
        as_of=as_of,
    )
    if len(refs) > 100:
        raise AnalyticsValidationError(
            "Trend evidence exceeds the context limit; narrow the window."
        )
    return build_trend_result(
        metric,
        points,
        definition=definition,
        from_date=from_date,
        to_date=to_date,
        timezone=timezone,
        evidence_refs=refs,
    )


def compute_associations(
    session: Session,
    owner_id: UUID,
    pair_ids: list[str],
    from_date: date,
    to_date: date,
    timezone: str,
    *,
    prepared_series: dict[str, MetricSeries] | None = None,
) -> list[StoredSignal]:
    if not pair_ids or len(pair_ids) > 5 or len(set(pair_ids)) != len(pair_ids):
        raise AnalyticsValidationError("Select between one and five distinct supported pairs.")
    try:
        pairs = [ASSOCIATION_PAIRS[pair_id] for pair_id in pair_ids]
    except KeyError as exc:
        raise AnalyticsValidationError("One or more association pairs are not supported.") from exc
    if (to_date - from_date).days + 1 > MAX_ANALYSIS_DAYS:
        raise AnalyticsValidationError("The selected range cannot exceed 366 days.")
    metric_names = sorted({str(value) for pair in pairs for value in (pair.first, pair.second)})
    series_by_metric = prepared_series
    if series_by_metric is None:
        snapshot = load_analytics_snapshot(session, owner_id, from_date, to_date, timezone)
        series_by_metric = {
            metric: _series_from_snapshot(
                metric,
                metric_definition(session, owner_id, metric),
                from_date,
                to_date,
                timezone,
                snapshot,
            )
            for metric in metric_names
        }
    elif any(metric not in series_by_metric for metric in metric_names):
        raise AnalyticsValidationError("The prepared association inputs are incomplete.")
    results: list[tuple[AssociationPair, AssociationResult, list[EvidenceReference]]] = []
    for pair in pairs:
        _, first_points, first_refs, _ = series_by_metric[str(pair.first)]
        _, second_points, second_refs, _ = series_by_metric[str(pair.second)]
        refs_by_key = {
            (ref.object_id, ref.revision, ref.object_type): ref
            for ref in (*first_refs, *second_refs)
        }
        refs = sorted(refs_by_key.values(), key=lambda ref: (str(ref.object_id), ref.revision))
        result = build_association_result(
            pair,
            first_points,
            second_points,
            from_date=from_date,
            to_date=to_date,
            timezone=timezone,
            evidence_refs=refs,
        )
        results.append((pair, result, refs))
    session.commit()
    generations = {series_by_metric[metric][3] for metric in metric_names}
    if len(generations) != 1:
        raise AnalyticsConflict("Health data changed during analysis. Refresh the result.")
    expected_generation = generations.pop()
    start_at = local_day_bounds(from_date, timezone)[0]
    end_at = local_day_bounds(to_date + timedelta(days=1), timezone)[0]
    stored: list[StoredSignal] = []
    for pair, result, refs in results:
        pair_id = pair.id
        scope_key = _signal_scope(pair_id, from_date, to_date, timezone)
        fingerprint = _sha256(
            {
                "method": result.method_version,
                "result": result.model_dump(mode="json"),
                "evidence": [ref.model_dump(mode="json") for ref in refs],
            }
        )
        payload = {
            "signal_kind": "association",
            "metric": pair_id,
            "title": pair_id.replace(":", " and ").replace("_", " ").title(),
            "result": result.model_dump(mode="json"),
        }
        obj, artifact = _persist_signal(
            session,
            owner_id,
            scope_key=scope_key,
            input_fingerprint=fingerprint,
            payload=payload,
            evidence_refs=refs,
            valid_from=start_at,
            valid_to=end_at,
            expected_generation=expected_generation,
        )
        stored.append(StoredSignal(obj, artifact, result, expected_generation))
    return stored


def generate_insights(
    session: Session,
    owner_id: UUID,
    metrics: list[str],
    association_pairs: list[str],
    from_date: date,
    to_date: date,
    timezone: str,
) -> tuple[list[StoredSignal], list[ArtifactAggregate]]:
    if (
        not metrics
        and not association_pairs
        or len(metrics) > 5
        or len(set(metrics)) != len(metrics)
        or len(association_pairs) > 5
        or len(set(association_pairs)) != len(association_pairs)
    ):
        raise AnalyticsValidationError(
            "Select distinct trend metrics or association pairs within the supported bounds."
        )
    if (to_date - from_date).days + 1 > MAX_ANALYSIS_DAYS:
        raise AnalyticsValidationError("The selected range cannot exceed 366 days.")
    for metric in metrics:
        metric_definition(session, owner_id, metric)
    if any(pair not in ASSOCIATION_PAIRS for pair in association_pairs):
        raise AnalyticsValidationError("One or more association pairs are not supported.")
    needed_metrics = set(metrics)
    for pair_id in association_pairs:
        pair = ASSOCIATION_PAIRS[pair_id]
        needed_metrics.update((str(pair.first), str(pair.second)))
    snapshot = load_analytics_snapshot(session, owner_id, from_date, to_date, timezone)
    prepared_series = {
        metric: _series_from_snapshot(
            metric,
            metric_definition(session, owner_id, metric),
            from_date,
            to_date,
            timezone,
            snapshot,
        )
        for metric in sorted(needed_metrics)
    }
    now = datetime.now(UTC)
    signals = [
        compute_trend(
            session,
            owner_id,
            metric,
            from_date,
            to_date,
            timezone,
            prepared_series=prepared_series[metric],
        )
        for metric in metrics
    ]
    if association_pairs:
        signals.extend(
            compute_associations(
                session,
                owner_id,
                association_pairs,
                from_date,
                to_date,
                timezone,
                prepared_series=prepared_series,
            )
        )
    insights: list[ArtifactAggregate] = []
    for signal in signals:
        insight = create_insight_from_signal(session, owner_id, signal, now)
        if insight is not None:
            insights.append(insight)
        recommendation = create_coverage_recommendation_from_signal(session, owner_id, signal, now)
        if recommendation is not None:
            insights.append(recommendation)
    return signals, insights
