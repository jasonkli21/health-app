"""Persistence, revalidation, and lifecycle operations for analytics artifacts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from math import fsum
from statistics import median
from typing import Any, Literal, cast
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from health_api.application.analytics_computation import _tracker_metric_parts
from health_api.application.analytics_contracts import (
    AnalyticsConflict,
    AnalyticsNotFound,
    AnalyticsValidationError,
    ArtifactAggregate,
    StoredSignal,
    _sha256,
)
from health_api.application.analytics_sources import _series, metric_definition
from health_api.application.envelope_service import manual_source, unit_of_work
from health_api.application.today_service import (
    owner_today_settings,
)
from health_api.domain.analytics import (
    INSIGHT_TEMPLATE_VERSION,
    METRIC_CATALOG,
    AssociationResult,
    DailyMetricPoint,
    EvidenceReference,
    ExperimentPayloadV1,
    ExperimentPeriodResult,
    ExperimentResult,
    InsightEvidenceReference,
    InsightPayloadV1,
    RecommendationPayloadV1,
    TrendResult,
)
from health_api.persistence.models import (
    AnalyticsArtifact,
    AnalyticsEvidence,
    HealthObject,
    HealthObjectRevision,
    PlanningResource,
    Source,
    User,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session


def _source(session: Session, owner_id: UUID, kind: Literal["manual", "system"]) -> Source:
    if kind == "manual":
        return manual_source(session, owner_id)
    session.execute(
        insert(Source)
        .values(
            owner_id=owner_id,
            source_key="health-analytics",
            source_kind="system",
            display_name="Health analytics",
        )
        .on_conflict_do_nothing(index_elements=[Source.owner_id, Source.source_key])
    )
    source = session.scalar(
        select(Source).where(Source.owner_id == owner_id, Source.source_key == "health-analytics")
    )
    if source is None or source.source_kind != "system":
        raise RuntimeError("analytics provenance source could not be resolved")
    return source


def _snapshot(obj: HealthObject, artifact: AnalyticsArtifact) -> dict[str, Any]:
    return {
        "object_id": str(obj.id),
        "object_type": obj.object_type,
        "domain": obj.domain,
        "status": obj.status,
        "title": obj.title,
        "valid_from": obj.valid_from.isoformat() if obj.valid_from else None,
        "valid_to": obj.valid_to.isoformat() if obj.valid_to else None,
        "recorded_at": obj.recorded_at.isoformat() if obj.recorded_at else None,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
        "source_id": str(obj.source_id),
        "confirmation_status": obj.confirmation_status,
        "schema_version": obj.schema_version,
        "revision": obj.revision,
        "notes": obj.notes,
        "metadata": obj.metadata_json,
        "ai_use_allowed": obj.ai_use_allowed,
        "cross_domain_use_allowed": obj.cross_domain_use_allowed,
        "artifact_kind": artifact.artifact_kind,
        "state": artifact.state,
        "scope_key": artifact.scope_key,
        "dedupe_key": artifact.dedupe_key,
        "payload": artifact.payload,
    }


def _append_revision(
    session: Session,
    owner_id: UUID,
    obj: HealthObject,
    artifact: AnalyticsArtifact,
    reason: Literal["create", "update"],
) -> None:
    session.add(
        HealthObjectRevision(
            owner_id=owner_id,
            object_id=obj.id,
            revision=obj.revision,
            actor_kind="user",
            actor_id=owner_id,
            reason=reason,
            snapshot=_snapshot(obj, artifact),
        )
    )


def _set_artifact_state(
    session: Session,
    owner_id: UUID,
    obj: HealthObject,
    artifact: AnalyticsArtifact,
    state: str,
) -> None:
    if artifact.state == state:
        return
    artifact.state = state
    artifact.payload = {**artifact.payload, "state": state}
    obj.revision += 1
    obj.updated_at = datetime.now(UTC)
    session.flush()
    _append_revision(session, owner_id, obj, artifact, "update")
    session.flush()
    if artifact.artifact_kind == "derived_signal" and state == "stale":
        dependent_rows = session.execute(
            select(AnalyticsArtifact, HealthObject)
            .join(
                AnalyticsEvidence,
                and_(
                    AnalyticsEvidence.owner_id == AnalyticsArtifact.owner_id,
                    AnalyticsEvidence.artifact_object_id == AnalyticsArtifact.object_id,
                ),
            )
            .join(
                HealthObject,
                and_(
                    HealthObject.owner_id == AnalyticsArtifact.owner_id,
                    HealthObject.id == AnalyticsArtifact.object_id,
                ),
            )
            .where(
                AnalyticsEvidence.owner_id == owner_id,
                AnalyticsEvidence.evidence_object_id == obj.id,
                AnalyticsArtifact.artifact_kind.in_(("insight", "recommendation")),
                AnalyticsArtifact.state.in_(("current", "proposed", "accepted")),
            )
            .order_by(AnalyticsArtifact.object_id)
        ).all()
        for dependent, dependent_obj in dependent_rows:
            _set_artifact_state(session, owner_id, dependent_obj, dependent, "stale")


def _lock_owner(session: Session, owner_id: UUID) -> int:
    sequence = session.scalar(
        select(User.daily_sequence)
        .where(User.id == owner_id, User.lifecycle == "active")
        .with_for_update()
    )
    if sequence is None:
        raise AnalyticsNotFound
    return sequence


def _validate_evidence_current(
    session: Session,
    owner_id: UUID,
    evidence_refs: list[EvidenceReference] | list[InsightEvidenceReference],
) -> None:
    by_id = {reference.object_id: reference for reference in evidence_refs}
    if not by_id:
        return
    rows = session.execute(
        select(
            HealthObject.id, HealthObject.revision, HealthObject.status, HealthObject.object_type
        ).where(HealthObject.owner_id == owner_id, HealthObject.id.in_(by_id))
    ).all()
    current = {
        object_id: (revision, status, object_type)
        for object_id, revision, status, object_type in rows
    }
    for object_id, reference in by_id.items():
        values = current.get(object_id)
        if (
            values is None
            or values[0] != reference.revision
            or values[1] != "active"
            or values[2] != reference.object_type
        ):
            raise AnalyticsConflict("Health data changed during analysis. Refresh the result.")
    signal_ids = [
        object_id
        for object_id, reference in by_id.items()
        if reference.object_type == "derived_signal"
    ]
    if signal_ids:
        signal_states = dict(
            session.execute(
                select(AnalyticsArtifact.object_id, AnalyticsArtifact.state).where(
                    AnalyticsArtifact.owner_id == owner_id,
                    AnalyticsArtifact.object_id.in_(signal_ids),
                    AnalyticsArtifact.artifact_kind == "derived_signal",
                )
            ).all()
        )
        if any(signal_states.get(object_id) != "current" for object_id in signal_ids):
            raise AnalyticsConflict("The linked analysis result is stale. Refresh it.")


def _invalidate_referenced(
    session: Session,
    owner_id: UUID,
    object_ids: set[UUID] | None,
) -> None:
    kinds = ("derived_signal", "insight", "recommendation")
    query = (
        select(AnalyticsArtifact, HealthObject)
        .join(
            HealthObject,
            and_(
                HealthObject.owner_id == AnalyticsArtifact.owner_id,
                HealthObject.id == AnalyticsArtifact.object_id,
            ),
        )
        .where(
            AnalyticsArtifact.owner_id == owner_id,
            AnalyticsArtifact.artifact_kind.in_(kinds),
            AnalyticsArtifact.state.in_(("current", "proposed", "accepted")),
        )
        .order_by(AnalyticsArtifact.object_id)
    )
    if object_ids is not None:
        if not object_ids:
            return
        query = query.join(
            AnalyticsEvidence,
            and_(
                AnalyticsEvidence.owner_id == AnalyticsArtifact.owner_id,
                AnalyticsEvidence.artifact_object_id == AnalyticsArtifact.object_id,
            ),
        ).where(AnalyticsEvidence.evidence_object_id.in_(object_ids))
    for artifact, obj in session.execute(query).all():
        _set_artifact_state(session, owner_id, obj, artifact, "stale")


def invalidate_analytics(
    session: Session,
    owner_id: UUID,
    *,
    object_ids: set[UUID] | None = None,
) -> None:
    """Invalidate evidence-bound outputs in the same transaction as a daily write.

    A newly created row has no prior evidence edge. Updates can also introduce
    a previously unrelated row into a saved scope, so callers use ``None`` for
    edits and inserts. Archives may pass IDs because the old evidence edge is
    sufficient to find every affected snapshot.
    """
    with unit_of_work(session):
        _invalidate_referenced(session, owner_id, object_ids)


def _signal_scope(metric_or_pair: str, from_date: date, to_date: date, timezone: str) -> str:
    return _sha256(
        {
            "metric": metric_or_pair,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "timezone": timezone,
        }
    )


def _persist_signal(
    session: Session,
    owner_id: UUID,
    *,
    scope_key: str,
    input_fingerprint: str,
    payload: dict[str, Any],
    evidence_refs: list[EvidenceReference],
    valid_from: datetime,
    valid_to: datetime,
    expected_generation: int,
) -> ArtifactAggregate:
    """Persist a result after revalidating its source generation and evidence.

    Calculations run before the write transaction. The owner lock, generation
    comparison, and exact evidence checks below prevent a stale snapshot from
    becoming a current artifact.
    """
    dedupe_key = _sha256({"scope": scope_key, "fingerprint": input_fingerprint})
    object_id = uuid5(owner_id, f"health-analytics:derived_signal:{dedupe_key}")
    title = str(payload.get("title") or payload.get("metric") or "Derived health signal")[:120]
    fingerprint = _sha256(
        {"artifact_kind": "derived_signal", "payload": payload, "dedupe_key": dedupe_key}
    )
    with unit_of_work(session):
        generation = _lock_owner(session, owner_id)
        if generation != expected_generation:
            raise AnalyticsConflict("Health data changed during analysis. Refresh the result.")
        _validate_evidence_current(session, owner_id, evidence_refs)
        siblings = session.execute(
            select(AnalyticsArtifact, HealthObject)
            .join(
                HealthObject,
                and_(
                    HealthObject.owner_id == AnalyticsArtifact.owner_id,
                    HealthObject.id == AnalyticsArtifact.object_id,
                ),
            )
            .where(
                AnalyticsArtifact.owner_id == owner_id,
                AnalyticsArtifact.artifact_kind == "derived_signal",
                AnalyticsArtifact.scope_key == scope_key,
                AnalyticsArtifact.state == "current",
            )
        ).all()
        for sibling, sibling_obj in siblings:
            if sibling.dedupe_key != dedupe_key:
                _set_artifact_state(session, owner_id, sibling_obj, sibling, "stale")
        existing = session.scalar(
            select(AnalyticsArtifact).where(
                AnalyticsArtifact.owner_id == owner_id,
                AnalyticsArtifact.artifact_kind == "derived_signal",
                AnalyticsArtifact.dedupe_key == dedupe_key,
            )
        )
        if existing is not None:
            obj = session.scalar(
                select(HealthObject).where(
                    HealthObject.owner_id == owner_id, HealthObject.id == existing.object_id
                )
            )
            if obj is None:
                raise RuntimeError("derived signal has no canonical object")
            if existing.state != "current":
                _set_artifact_state(session, owner_id, obj, existing, "current")
            return obj, existing
        source = _source(session, owner_id, "system")
        obj = HealthObject(
            id=object_id,
            owner_id=owner_id,
            object_type="derived_signal",
            domain="analytics",
            status="active",
            title=title,
            valid_from=valid_from,
            valid_to=valid_to,
            source_id=source.id,
            confirmation_status="unconfirmed",
            schema_version=1,
            revision=1,
            notes=None,
            metadata_json={},
            ai_use_allowed=False,
            cross_domain_use_allowed=False,
            create_fingerprint=fingerprint,
        )
        artifact = AnalyticsArtifact(
            owner_id=owner_id,
            object_id=object_id,
            artifact_kind="derived_signal",
            state="current",
            scope_key=scope_key,
            dedupe_key=dedupe_key,
            payload={**payload, "state": "current", "input_fingerprint": input_fingerprint},
        )
        session.add_all([obj, artifact])
        session.flush()
        _append_revision(session, owner_id, obj, artifact, "create")
        if evidence_refs:
            session.add_all(
                [
                    AnalyticsEvidence(
                        owner_id=owner_id,
                        artifact_object_id=object_id,
                        evidence_object_id=reference.object_id,
                        evidence_revision=reference.revision,
                        evidence_object_type=reference.object_type,
                    )
                    for reference in evidence_refs
                ]
            )
        session.flush()
        return obj, artifact


def _persist_object_artifact(
    session: Session,
    owner_id: UUID,
    *,
    artifact_kind: Literal["insight", "recommendation", "experiment"],
    object_id: UUID,
    title: str,
    payload: dict[str, Any],
    state: str,
    dedupe_key: str | None,
    scope_key: str | None = None,
    evidence_refs: list[InsightEvidenceReference] | None = None,
    validity: tuple[datetime | None, datetime | None] = (None, None),
) -> ArtifactAggregate:
    _lock_owner(session, owner_id)
    _validate_evidence_current(session, owner_id, evidence_refs or [])
    if artifact_kind in ("insight", "recommendation"):
        signal_ref = next(
            (ref for ref in evidence_refs or [] if ref.object_type == "derived_signal"),
            None,
        )
        if signal_ref is not None:
            prior_decision = _prior_artifact_decision(
                session, owner_id, artifact_kind, signal_ref.object_id
            )
            if prior_decision is not None:
                payload = {**payload, "state": prior_decision, "decision": prior_decision}
                state = prior_decision
    fingerprint = _sha256(
        {"artifact_kind": artifact_kind, "payload": payload, "dedupe_key": dedupe_key}
    )
    existing = (
        session.scalar(
            select(AnalyticsArtifact)
            .where(
                AnalyticsArtifact.owner_id == owner_id,
                AnalyticsArtifact.artifact_kind == artifact_kind,
                AnalyticsArtifact.dedupe_key == dedupe_key,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if dedupe_key is not None
        else None
    )
    if existing is not None:
        obj = session.scalar(
            select(HealthObject)
            .where(HealthObject.owner_id == owner_id, HealthObject.id == existing.object_id)
            .execution_options(populate_existing=True)
        )
        if obj is None:
            raise RuntimeError("analytics artifact has no canonical object")
        existing_payload = existing.payload
        decision = existing_payload.get("decision")
        if decision in ("accepted", "dismissed") or existing.state in (
            "accepted",
            "dismissed",
        ):
            return obj, existing
        if prior_decision is not None:
            existing.payload = {
                **payload,
                "state": prior_decision,
                "decision": prior_decision,
            }
            existing.state = prior_decision
            obj.title = title[:120]
            obj.valid_from, obj.valid_to = validity
            obj.revision += 1
            obj.updated_at = datetime.now(UTC)
            session.flush()
            _append_revision(session, owner_id, obj, existing, "update")
            session.flush()
            return obj, existing
        if existing.state in ("stale", "expired") and state in ("current", "proposed"):
            existing.payload = {**payload, "state": state}
            existing.state = state
            existing.scope_key = scope_key
            obj.valid_from, obj.valid_to = validity
            obj.revision += 1
            obj.updated_at = datetime.now(UTC)
            session.flush()
            _append_revision(session, owner_id, obj, existing, "update")
            session.flush()
        return obj, existing
    if artifact_kind == "experiment":
        existing_obj = session.scalar(
            select(HealthObject).where(
                HealthObject.owner_id == owner_id,
                HealthObject.id == object_id,
                HealthObject.object_type == "experiment",
            )
        )
        if existing_obj is not None:
            existing_artifact = session.get(AnalyticsArtifact, (owner_id, object_id))
            if existing_artifact is not None and existing_obj.create_fingerprint == fingerprint:
                return existing_obj, existing_artifact
    occupied = session.scalar(select(HealthObject).where(HealthObject.id == object_id))
    if occupied is not None:
        raise AnalyticsConflict("This experiment ID is already in use.")
    source = _source(session, owner_id, "manual" if artifact_kind == "experiment" else "system")
    obj = HealthObject(
        id=object_id,
        owner_id=owner_id,
        object_type=artifact_kind,
        domain="analytics",
        status="active",
        title=title[:120],
        valid_from=validity[0],
        valid_to=validity[1],
        source_id=source.id,
        confirmation_status="user_confirmed" if artifact_kind == "experiment" else "unconfirmed",
        schema_version=1,
        revision=1,
        notes=None,
        metadata_json={},
        ai_use_allowed=False,
        cross_domain_use_allowed=False,
        create_fingerprint=fingerprint,
    )
    artifact = AnalyticsArtifact(
        owner_id=owner_id,
        object_id=object_id,
        artifact_kind=artifact_kind,
        state=state,
        scope_key=scope_key,
        dedupe_key=dedupe_key,
        payload=payload if artifact_kind == "experiment" else {**payload, "state": state},
    )
    session.add_all([obj, artifact])
    session.flush()
    _append_revision(session, owner_id, obj, artifact, "create")
    if evidence_refs:
        session.add_all(
            [
                AnalyticsEvidence(
                    owner_id=owner_id,
                    artifact_object_id=object_id,
                    evidence_object_id=ref.object_id,
                    evidence_revision=ref.revision,
                    evidence_object_type=ref.object_type,
                )
                for ref in evidence_refs
            ]
        )
    session.flush()
    return obj, artifact


def _prior_artifact_decision(
    session: Session,
    owner_id: UUID,
    kind: Literal["insight", "recommendation"],
    signal_id: UUID,
) -> Literal["accepted", "dismissed"] | None:
    artifacts = session.scalars(
        select(AnalyticsArtifact)
        .join(
            AnalyticsEvidence,
            and_(
                AnalyticsEvidence.owner_id == AnalyticsArtifact.owner_id,
                AnalyticsEvidence.artifact_object_id == AnalyticsArtifact.object_id,
            ),
        )
        .join(
            HealthObject,
            and_(
                HealthObject.owner_id == AnalyticsArtifact.owner_id,
                HealthObject.id == AnalyticsArtifact.object_id,
            ),
        )
        .where(
            AnalyticsArtifact.owner_id == owner_id,
            AnalyticsArtifact.artifact_kind == kind,
            AnalyticsEvidence.evidence_object_id == signal_id,
            AnalyticsEvidence.evidence_object_type == "derived_signal",
        )
        .order_by(HealthObject.updated_at.desc(), HealthObject.id.desc())
        .execution_options(populate_existing=True)
    ).all()
    for artifact in artifacts:
        payload = artifact.payload
        decision = payload.get("decision")
        if decision == "accepted" or decision == "dismissed":
            return cast(Literal["accepted", "dismissed"], decision)
        if artifact.state in ("accepted", "dismissed"):
            return cast(Literal["accepted", "dismissed"], artifact.state)
        historical_states: list[dict[str, Any]] = list(
            session.scalars(
                select(HealthObjectRevision.snapshot)
                .where(
                    HealthObjectRevision.owner_id == owner_id,
                    HealthObjectRevision.object_id == artifact.object_id,
                )
                .order_by(HealthObjectRevision.revision.desc())
            ).all()
        )
        for snapshot in historical_states:
            prior_state = snapshot.get("state")
            if prior_state in ("accepted", "dismissed"):
                return cast(Literal["accepted", "dismissed"], prior_state)
    return None


def create_insight_from_signal(
    session: Session,
    owner_id: UUID,
    signal: StoredSignal,
    now: datetime,
) -> ArtifactAggregate | None:
    if isinstance(signal.result, TrendResult):
        trend = signal.result
        comparison = trend.comparison
        if comparison is None or comparison.before.mean is None or comparison.after.mean is None:
            return None
        before = comparison.before.mean
        after = comparison.after.mean
        direction = (
            "was unchanged" if after == before else "was higher" if after > before else "was lower"
        )
        explanation = (
            f"{trend.label} {direction} in the later half of this window: "
            f"{after:.3g} {trend.unit} compared with {before:.3g} {trend.unit} in the earlier half. "
            "This is a descriptive comparison, not a measure of clinical importance."
        )
        title = f"{trend.label}: descriptive change"
        insight_kind: Literal["trend", "association", "coverage"] = "trend"
        method_version: str = trend.method_version
        source_refs = trend.evidence_refs
        uncertainty = (
            "Logged data may be sparse or incomplete. Changes are descriptive and do not establish "
            "clinical meaning or cause."
        )
    elif isinstance(signal.result, AssociationResult):
        association = signal.result
        if association.status != "available" or association.rho is None:
            return None
        first = METRIC_CATALOG[association.pair.first]
        second = METRIC_CATALOG[association.pair.second]
        explanation = (
            f"Across {association.paired_days} paired days, {first.label.lower()} and "
            f"{second.label.lower()} had a same-day Spearman rank correlation of "
            f"{association.rho:.2f}. Association only; confounding and reporting bias are possible."
        )
        title = f"Association observed: {first.label} and {second.label}"
        insight_kind = "association"
        method_version = association.method_version
        source_refs = association.evidence_refs
        uncertainty = association.limitation
    else:
        return None
    expires_at = now + timedelta(days=7)
    refs = [
        InsightEvidenceReference(
            object_id=signal.obj.id,
            revision=signal.obj.revision,
            object_type="derived_signal",
        ),
        *[
            InsightEvidenceReference(
                object_id=ref.object_id,
                revision=ref.revision,
                object_type=ref.object_type,
            )
            for ref in source_refs
        ],
    ]
    dedupe_key = _sha256(
        {
            "template": INSIGHT_TEMPLATE_VERSION,
            "signal_id": str(signal.obj.id),
            "signal_revision": signal.obj.revision,
        }
    )
    object_id = uuid5(owner_id, f"health-analytics:insight:{dedupe_key}")
    payload_model = InsightPayloadV1(
        title=title,
        explanation=explanation,
        kind=insight_kind,
        evidence_refs=refs,
        uncertainty=uncertainty,
        method_version=method_version,
        valid_from=now,
        expires_at=expires_at,
        state="current",
    )
    session.commit()
    with unit_of_work(session):
        return _persist_object_artifact(
            session,
            owner_id,
            artifact_kind="insight",
            object_id=object_id,
            title=payload_model.title,
            payload=payload_model.model_dump(mode="json"),
            state="current",
            dedupe_key=dedupe_key,
            evidence_refs=refs,
            validity=(now, expires_at),
        )


def create_coverage_recommendation_from_signal(
    session: Session,
    owner_id: UUID,
    signal: StoredSignal,
    now: datetime,
) -> ArtifactAggregate | None:
    if not isinstance(signal.result, TrendResult):
        return None
    trend = signal.result
    if trend.coverage.missing_days == 0 or trend.coverage.calendar_days < 7:
        return None
    refs = [
        InsightEvidenceReference(
            object_id=signal.obj.id,
            revision=signal.obj.revision,
            object_type="derived_signal",
        ),
        *[
            InsightEvidenceReference(
                object_id=ref.object_id,
                revision=ref.revision,
                object_type=ref.object_type,
            )
            for ref in trend.evidence_refs
        ],
    ]
    dedupe_key = _sha256(
        {
            "suggestion": "coverage-v1",
            "signal_id": str(signal.obj.id),
            "signal_revision": signal.obj.revision,
        }
    )
    object_id = uuid5(owner_id, f"health-analytics:recommendation:{dedupe_key}")
    expires_at = now + timedelta(days=7)
    payload_model = RecommendationPayloadV1(
        title="Improve trend coverage",
        suggestion=(
            f"If it is useful to you, keep logging {trend.label.lower()} on upcoming days so future "
            "summaries can show a clearer pattern."
        ),
        rationale=(
            f"{trend.coverage.missing_days} of {trend.coverage.calendar_days} calendar days in this "
            "window have no known value."
        ),
        risk_class="low",
        evidence_refs=refs,
        expected_review_context="This is a tracking suggestion only; it does not advise a health intervention.",
        generated_by="deterministic",
        created_at=now,
        expires_at=expires_at,
        state="proposed",
    )
    session.commit()
    with unit_of_work(session):
        return _persist_object_artifact(
            session,
            owner_id,
            artifact_kind="recommendation",
            object_id=object_id,
            title=payload_model.title,
            payload=payload_model.model_dump(mode="json"),
            state="proposed",
            dedupe_key=dedupe_key,
            evidence_refs=refs,
            validity=(now, expires_at),
        )


def _artifact_aggregate(
    session: Session, owner_id: UUID, artifact_id: UUID, kind: str
) -> ArtifactAggregate:
    row = session.execute(
        select(HealthObject, AnalyticsArtifact)
        .join(
            AnalyticsArtifact,
            and_(
                AnalyticsArtifact.owner_id == HealthObject.owner_id,
                AnalyticsArtifact.object_id == HealthObject.id,
            ),
        )
        .where(
            HealthObject.owner_id == owner_id,
            HealthObject.id == artifact_id,
            AnalyticsArtifact.artifact_kind == kind,
        )
    ).one_or_none()
    if row is None:
        raise AnalyticsNotFound
    return row


def list_artifacts(
    session: Session,
    owner_id: UUID,
    kind: Literal["insight", "recommendation", "experiment"],
    *,
    state: str | None,
    limit: int,
    after: tuple[datetime, UUID] | None = None,
) -> list[ArtifactAggregate]:
    conditions: list[Any] = [
        AnalyticsArtifact.owner_id == owner_id,
        AnalyticsArtifact.artifact_kind == kind,
        HealthObject.status == "active",
    ]
    now = datetime.now(UTC)
    cursor = after
    matched: list[ArtifactAggregate] = []
    while len(matched) < limit:
        batch_conditions = list(conditions)
        if cursor is not None:
            after_created, after_id = cursor
            batch_conditions.append(
                or_(
                    HealthObject.created_at < after_created,
                    and_(HealthObject.created_at == after_created, HealthObject.id < after_id),
                )
            )
        rows = list(
            session.execute(
                select(HealthObject, AnalyticsArtifact)
                .join(
                    AnalyticsArtifact,
                    and_(
                        AnalyticsArtifact.owner_id == HealthObject.owner_id,
                        AnalyticsArtifact.object_id == HealthObject.id,
                    ),
                )
                .where(*batch_conditions)
                .order_by(HealthObject.created_at.desc(), HealthObject.id.desc())
                .limit(max(limit, 50))
            ).all()
        )
        if not rows:
            break
        for obj, artifact in rows:
            cursor = (obj.created_at, obj.id)
            effective_state = artifact.state
            if artifact.artifact_kind == "insight":
                expiry = InsightPayloadV1.model_validate(artifact.payload).expires_at
            elif artifact.artifact_kind == "recommendation":
                expiry = RecommendationPayloadV1.model_validate(artifact.payload).expires_at
            else:
                expiry = None
            if (
                expiry is not None
                and expiry <= now
                and artifact.state not in ("expired", "dismissed", "stale")
            ):
                effective_state = "expired"
            if state is None or effective_state == state:
                matched.append((obj, artifact))
                if len(matched) == limit:
                    break
        if len(rows) < max(limit, 50):
            break
    return matched


def _update_artifact(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    kind: Literal["insight", "recommendation", "experiment"],
    expected_revision: int,
    payload: dict[str, Any],
    state: str,
) -> ArtifactAggregate:
    # Authentication and the initial scoped lookup may have opened a read
    # transaction; end it before the durable optimistic update transaction.
    session.commit()
    with unit_of_work(session):
        _lock_owner(session, owner_id)
        obj = session.scalar(
            select(HealthObject)
            .where(HealthObject.owner_id == owner_id, HealthObject.id == object_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        artifact = session.scalar(
            select(AnalyticsArtifact)
            .where(
                AnalyticsArtifact.owner_id == owner_id,
                AnalyticsArtifact.object_id == object_id,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if obj is None or artifact is None or artifact.artifact_kind != kind:
            raise AnalyticsNotFound
        if obj.revision != expected_revision:
            raise AnalyticsConflict("The analytics item changed. Reload it before saving.")
        if kind == "experiment" and artifact.state == "draft":
            experiment_payload = ExperimentPayloadV1.model_validate(payload)
            metric_definition(session, owner_id, experiment_payload.outcome_metric)
            if state == "active":
                _validate_experiment_start(session, owner_id, experiment_payload)
            else:
                _validate_experiment_reference(session, owner_id, experiment_payload)
        if (
            kind == "experiment"
            and artifact.state == "active"
            and state
            in (
                "completed",
                "stopped",
            )
        ):
            experiment_payload = ExperimentPayloadV1.model_validate(payload)
            _, timezone = owner_today_settings(session, owner_id)
            today = datetime.now(ZoneInfo(timezone)).date()
            if today < experiment_payload.start_date:
                raise AnalyticsValidationError(
                    "An experiment cannot stop before its planned intervention starts."
                )
            actual_end = datetime.now(UTC)
            payload = experiment_payload.model_copy(
                update={"actual_end_at": actual_end}
            ).model_dump(mode="json")
        if kind in ("insight", "recommendation") and artifact.state in (
            "expired",
            "stale",
            "dismissed",
            "accepted",
        ):
            raise AnalyticsConflict("This analytics item can no longer be changed.")
        if kind == "experiment" and artifact.state == "archived":
            raise AnalyticsConflict("This experiment can no longer be changed.")
        artifact.payload = payload if kind == "experiment" else {**payload, "state": state}
        artifact.state = state
        if kind == "experiment":
            obj.title = "Experiment: " + str(payload.get("hypothesis", ""))[:100]
        else:
            obj.title = str(payload.get("title", obj.title))[:120]
        obj.revision += 1
        obj.updated_at = datetime.now(UTC)
        session.flush()
        _append_revision(session, owner_id, obj, artifact, "update")
        session.flush()
        return obj, artifact


def change_insight_state(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    expected_revision: int,
    state: Literal["dismissed"],
) -> ArtifactAggregate:
    _, artifact = _artifact_aggregate(session, owner_id, object_id, "insight")
    payload = InsightPayloadV1.model_validate(artifact.payload)
    now = datetime.now(UTC)
    if payload.expires_at <= now and artifact.state not in ("dismissed", "stale", "expired"):
        return _update_artifact(
            session,
            owner_id,
            object_id,
            "insight",
            expected_revision,
            payload.model_copy(update={"state": "expired"}).model_dump(mode="json"),
            "expired",
        )
    return _update_artifact(
        session,
        owner_id,
        object_id,
        "insight",
        expected_revision,
        payload.model_copy(update={"state": state, "decision": state}).model_dump(mode="json"),
        state,
    )


def change_recommendation_state(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    expected_revision: int,
    state: Literal["accepted", "dismissed"],
) -> ArtifactAggregate:
    _, artifact = _artifact_aggregate(session, owner_id, object_id, "recommendation")
    payload = RecommendationPayloadV1.model_validate(artifact.payload)
    now = datetime.now(UTC)
    if payload.expires_at <= now and artifact.state not in ("dismissed", "stale", "expired"):
        return _update_artifact(
            session,
            owner_id,
            object_id,
            "recommendation",
            expected_revision,
            payload.model_copy(update={"state": "expired"}).model_dump(mode="json"),
            "expired",
        )
    if artifact.state != "proposed":
        raise AnalyticsConflict("Only proposed recommendations can be accepted or dismissed.")
    return _update_artifact(
        session,
        owner_id,
        object_id,
        "recommendation",
        expected_revision,
        payload.model_copy(update={"state": state, "decision": state}).model_dump(mode="json"),
        state,
    )


def create_experiment(
    session: Session, owner_id: UUID, object_id: UUID, payload: ExperimentPayloadV1
) -> ArtifactAggregate:
    if payload.status != "draft":
        raise AnalyticsValidationError("New experiments must begin as drafts.")
    session.commit()
    with unit_of_work(session):
        _lock_owner(session, owner_id)
        metric_definition(session, owner_id, payload.outcome_metric)
        _validate_experiment_reference(session, owner_id, payload)
        return _persist_object_artifact(
            session,
            owner_id,
            artifact_kind="experiment",
            object_id=object_id,
            title="Experiment: " + payload.hypothesis[:100],
            payload=payload.model_dump(mode="json"),
            state="draft",
            dedupe_key=None,
        )


def _validate_experiment_reference(
    session: Session, owner_id: UUID, payload: ExperimentPayloadV1
) -> None:
    if payload.linked_resource is None:
        return
    reference = payload.linked_resource
    obj = session.scalar(
        select(HealthObject)
        .where(
            HealthObject.owner_id == owner_id,
            HealthObject.id == reference.object_id,
            HealthObject.status == "active",
            HealthObject.object_type == reference.object_type,
            HealthObject.revision == reference.revision,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    resource = session.scalar(
        select(PlanningResource)
        .where(
            PlanningResource.owner_id == owner_id,
            PlanningResource.object_id == reference.object_id,
            PlanningResource.resource_kind == reference.object_type,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if obj is None or resource is None or resource.lifecycle != "active":
        raise AnalyticsValidationError("The linked planning item is missing, archived, or changed.")


def _validate_experiment_start(
    session: Session, owner_id: UUID, payload: ExperimentPayloadV1
) -> None:
    _validate_experiment_reference(session, owner_id, payload)
    tracker_parts = _tracker_metric_parts(payload.outcome_metric)
    if tracker_parts is not None:
        tracker_id, _, _ = tracker_parts
        active_tracker = session.execute(
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
                PlanningResource.resource_kind == "tracker_definition",
                PlanningResource.lifecycle == "active",
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        ).one_or_none()
        if active_tracker is None:
            raise AnalyticsValidationError(
                "An experiment requires an active numeric tracker definition."
            )
    metric_definition(session, owner_id, payload.outcome_metric)
    _, timezone = owner_today_settings(session, owner_id)
    today = datetime.now(ZoneInfo(timezone)).date()
    if today < payload.start_date or today > payload.end_date:
        raise AnalyticsValidationError(
            "An experiment can start only during its planned intervention dates."
        )
    _, baseline_points, _, _ = _series(
        session,
        owner_id,
        payload.outcome_metric,
        payload.baseline_start,
        payload.start_date - timedelta(days=1),
        timezone,
    )
    if not any(point.value is not None for point in baseline_points):
        raise AnalyticsValidationError(
            "Log at least one known baseline outcome before starting this experiment."
        )


def update_experiment(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    expected_revision: int,
    payload: ExperimentPayloadV1,
) -> ArtifactAggregate:
    _, artifact = _artifact_aggregate(session, owner_id, object_id, "experiment")
    current = ExperimentPayloadV1.model_validate(artifact.payload)
    candidate = payload.model_dump(mode="json")
    original = current.model_dump(mode="json")
    candidate["status"] = current.status
    if current.status != "draft":
        for immutable in (
            "hypothesis",
            "intervention",
            "linked_resource",
            "outcome_metric",
            "baseline_start",
            "start_date",
            "end_date",
            "actual_end_at",
        ):
            candidate[immutable] = original[immutable]
    payload = ExperimentPayloadV1.model_validate(candidate)
    return _update_artifact(
        session,
        owner_id,
        object_id,
        "experiment",
        expected_revision,
        payload.model_dump(mode="json"),
        payload.status,
    )


def transition_experiment(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    expected_revision: int,
    target: Literal["active", "completed", "stopped", "archived"],
) -> ArtifactAggregate:
    _, artifact = _artifact_aggregate(session, owner_id, object_id, "experiment")
    payload = ExperimentPayloadV1.model_validate(artifact.payload)
    allowed = {
        "draft": {"active", "archived"},
        "active": {"completed", "stopped"},
        "completed": {"archived"},
        "stopped": {"archived"},
        "archived": set(),
    }
    if target not in allowed[payload.status]:
        raise AnalyticsConflict("This experiment lifecycle transition is not allowed.")
    updated = payload.model_copy(update={"status": target})
    return _update_artifact(
        session,
        owner_id,
        object_id,
        "experiment",
        expected_revision,
        updated.model_dump(mode="json"),
        target,
    )


def experiment_result(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    timezone: str,
) -> tuple[ArtifactAggregate, ExperimentResult]:
    aggregate = _artifact_aggregate(session, owner_id, object_id, "experiment")
    _, artifact = aggregate
    payload = ExperimentPayloadV1.model_validate(artifact.payload)
    if payload.status == "draft":
        raise AnalyticsValidationError("Start the experiment before viewing its results.")
    as_of = payload.actual_end_at or datetime.now(UTC)
    observed_end = min(payload.end_date, as_of.astimezone(ZoneInfo(timezone)).date())
    if observed_end < payload.start_date:
        observed_end = payload.start_date - timedelta(days=1)
    definition, points, refs, _ = _series(
        session,
        owner_id,
        payload.outcome_metric,
        payload.baseline_start,
        observed_end,
        timezone,
        as_of=as_of,
    )
    baseline_points = [
        point for point in points if payload.baseline_start <= point.date < payload.start_date
    ]
    intervention_points = [
        point for point in points if payload.start_date <= point.date <= observed_end
    ]

    def summarize_period(
        values: list[DailyMetricPoint], start: date, end: date
    ) -> ExperimentPeriodResult:
        known = [point.value for point in values if point.value is not None]
        total_days = (end - start).days
        return ExperimentPeriodResult(
            from_date=start,
            to_date=end - timedelta(days=1),
            known_days=len(known),
            missing_days=total_days - len(known),
            mean=fsum(known) / len(known) if known else None,
            median=median(known) if known else None,
        )

    baseline = summarize_period(baseline_points, payload.baseline_start, payload.start_date)
    intervention = summarize_period(
        intervention_points, payload.start_date, observed_end + timedelta(days=1)
    )
    difference = (
        intervention.mean - baseline.mean
        if intervention.mean is not None and baseline.mean is not None
        else None
    )
    return aggregate, ExperimentResult(
        metric=payload.outcome_metric,
        unit=definition.unit,
        timezone=timezone,
        baseline=baseline,
        intervention=intervention,
        mean_difference=difference,
        method_version="experiment-descriptive-v1/unit-v1",
        evidence_refs=refs,
    )


def expire_artifact_for_response(
    session: Session, owner_id: UUID, obj: HealthObject, artifact: AnalyticsArtifact, now: datetime
) -> ArtifactAggregate:
    if artifact.artifact_kind == "insight":
        expires_at = InsightPayloadV1.model_validate(artifact.payload).expires_at
    elif artifact.artifact_kind == "recommendation":
        expires_at = RecommendationPayloadV1.model_validate(artifact.payload).expires_at
    else:
        return obj, artifact
    if expires_at <= now and artifact.state not in ("expired", "dismissed", "stale"):
        session.commit()
        with unit_of_work(session):
            _lock_owner(session, owner_id)
            locked = session.scalar(
                select(HealthObject)
                .where(HealthObject.owner_id == owner_id, HealthObject.id == obj.id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            current = session.scalar(
                select(AnalyticsArtifact)
                .where(
                    AnalyticsArtifact.owner_id == owner_id,
                    AnalyticsArtifact.object_id == obj.id,
                )
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            if locked is None or current is None:
                raise AnalyticsNotFound
            if current.state in ("expired", "dismissed", "stale"):
                return locked, current
            _set_artifact_state(session, owner_id, locked, current, "expired")
            return locked, current
    return obj, artifact
