"""Owner-scoped bounded analysis, immutable evidence, and manual experiments."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import fsum
from statistics import median
from typing import Any, Literal, cast
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import and_, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from health_api.application.envelope_service import manual_source, unit_of_work
from health_api.application.today_service import owner_today_settings
from health_api.domain.analytics import (
    ASSOCIATION_PAIRS,
    INSIGHT_TEMPLATE_VERSION,
    MAX_ANALYSIS_DAYS,
    MAX_ANALYSIS_ROWS,
    METRIC_CATALOG,
    AnalyticsMetric,
    AssociationPair,
    AssociationResult,
    DailyMetricPoint,
    EvidenceReference,
    ExperimentPayloadV1,
    ExperimentPeriodResult,
    ExperimentResult,
    InsightEvidenceReference,
    InsightPayloadV1,
    MetricDefinition,
    RecommendationPayloadV1,
    TrendResult,
    build_association_result,
    build_trend_result,
)
from health_api.domain.daily import local_day_bounds
from health_api.domain.daily_rollups import summarize_today
from health_api.domain.planning import TrackerDefinitionV1, TrackerFieldKind
from health_api.domain.schemas import (
    CustomTrackerValueV1,
    DailyDomain,
    EventSchemaV1,
    MetricKey,
    ObservationSchemaV1,
)
from health_api.persistence.models import (
    AnalyticsArtifact,
    AnalyticsEvidence,
    EventItem,
    EventObservationLink,
    HealthObject,
    HealthObjectRevision,
    ObservationItem,
    PlanningResource,
    Source,
    TrackerSchemaVersion,
    User,
)

ANALYTICS_QUERY_TIMEOUT_MS = 2_000
_TRACKER_METRIC = re.compile(
    r"^tracker:([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}):"
    r"([a-z][a-z0-9_]{0,31}):v([1-9][0-9]*)$"
)
_EVENT_METRICS: dict[str, tuple[DailyDomain, MetricKey]] = {
    "energy": (DailyDomain.NUTRITION, MetricKey.ENERGY),
    "exercise_duration": (DailyDomain.EXERCISE, MetricKey.DURATION),
    "exercise_distance": (DailyDomain.EXERCISE, MetricKey.DISTANCE),
    "sleep_duration": (DailyDomain.SLEEP, MetricKey.DURATION),
    "symptom_severity": (DailyDomain.SYMPTOMS, MetricKey.SYMPTOM_SEVERITY),
    "symptom_episode_count": (DailyDomain.SYMPTOMS, MetricKey.SYMPTOM_EPISODE_COUNT),
    "weight": (DailyDomain.MEASUREMENTS, MetricKey.WEIGHT),
    "temperature": (DailyDomain.MEASUREMENTS, MetricKey.TEMPERATURE),
    "systolic_pressure": (DailyDomain.MEASUREMENTS, MetricKey.SYSTOLIC_PRESSURE),
    "diastolic_pressure": (DailyDomain.MEASUREMENTS, MetricKey.DIASTOLIC_PRESSURE),
    "pulse": (DailyDomain.MEASUREMENTS, MetricKey.PULSE),
}


class AnalyticsNotFound(Exception):
    """An owner-scoped analytics artifact or referenced resource is unavailable."""


class AnalyticsConflict(Exception):
    """An optimistic revision or lifecycle transition is stale or unsupported."""


class AnalyticsValidationError(Exception):
    """An analysis request or experiment violates the supported contract."""


type ArtifactAggregate = tuple[HealthObject, AnalyticsArtifact]
type EventInput = tuple[HealthObject, EventItem, EventSchemaV1]
type ObservationInput = tuple[HealthObject, ObservationItem, ObservationSchemaV1]
type MetricSeries = tuple[MetricDefinition, list[DailyMetricPoint], list[EvidenceReference], int]


@dataclass(frozen=True)
class StoredSignal:
    obj: HealthObject
    artifact: AnalyticsArtifact
    result: TrendResult | AssociationResult
    input_generation: int


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


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


def _row_date_in_range(
    precision: str,
    local_date: date | None,
    instant: datetime | None,
    interval_end: datetime | None,
    start: date,
    end: date,
    timezone: str,
) -> bool:
    if precision == "date_only":
        return local_date is not None and start <= local_date <= end
    if instant is None:
        return False
    start_at = local_day_bounds(start, timezone)[0]
    if end == date.max:
        return False
    end_at = local_day_bounds(end + timedelta(days=1), timezone)[0]
    return instant < end_at and (interval_end > start_at if interval_end else instant >= start_at)


def _load_inputs(
    session: Session,
    owner_id: UUID,
    from_date: date,
    to_date: date,
    timezone: str,
    *,
    ai_permitted_only: bool = False,
    excluded_object_ids: set[UUID] | None = None,
    as_of: datetime | None = None,
) -> tuple[list[EventInput], list[ObservationInput], dict[UUID, set[UUID]]]:
    days = (to_date - from_date).days + 1
    if from_date > to_date or days > MAX_ANALYSIS_DAYS or to_date == date.max:
        raise AnalyticsValidationError("The selected range is too large or invalid.")
    try:
        start_at = local_day_bounds(from_date, timezone)[0]
        end_at = local_day_bounds(to_date + timedelta(days=1), timezone)[0]
    except (ValueError, OverflowError) as exc:
        raise AnalyticsValidationError("The selected date or timezone is invalid.") from exc
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text(f"SET LOCAL statement_timeout = '{ANALYTICS_QUERY_TIMEOUT_MS}ms'"))
    owner_conditions: list[Any] = [
        HealthObject.owner_id == owner_id,
        HealthObject.status == "active",
    ]
    if excluded_object_ids:
        owner_conditions.append(HealthObject.id.not_in(excluded_object_ids))
    if ai_permitted_only:
        owner_conditions.append(HealthObject.ai_use_allowed.is_(True))
    if as_of is not None:
        owner_conditions.extend(
            (
                or_(HealthObject.valid_from.is_(None), HealthObject.valid_from <= as_of),
                or_(HealthObject.valid_to.is_(None), HealthObject.valid_to > as_of),
            )
        )
        try:
            as_of_local_date = as_of.astimezone(ZoneInfo(timezone)).date()
        except (OverflowError, ValueError) as exc:
            raise AnalyticsValidationError("The selected context time is invalid.") from exc
        event_query_end = min(end_at, as_of) if as_of < end_at else end_at
        observation_query_end = event_query_end
    else:
        as_of_local_date = None
        event_query_end = end_at
        observation_query_end = end_at
    event_query = (
        select(HealthObject, EventItem)
        .join(
            EventItem,
            and_(
                EventItem.owner_id == HealthObject.owner_id, EventItem.object_id == HealthObject.id
            ),
        )
        .where(
            *owner_conditions,
            HealthObject.object_type == "event",
            or_(
                and_(
                    EventItem.time_precision == "date_only",
                    EventItem.local_date >= from_date,
                    EventItem.local_date <= (as_of_local_date or to_date),
                ),
                and_(
                    EventItem.time_precision == "instant",
                    EventItem.occurred_at < event_query_end,
                    or_(
                        and_(EventItem.ended_at.is_(None), EventItem.occurred_at >= start_at),
                        and_(EventItem.ended_at.is_not(None), EventItem.ended_at > start_at),
                    ),
                ),
            ),
        )
        .order_by(HealthObject.id)
        .limit(MAX_ANALYSIS_ROWS + 1)
    )
    event_rows = session.execute(event_query).all()
    if len(event_rows) > MAX_ANALYSIS_ROWS:
        raise AnalyticsValidationError(
            "The selected range contains too many health records; narrow it."
        )
    remaining = MAX_ANALYSIS_ROWS - len(event_rows)
    observation_query = (
        select(HealthObject, ObservationItem)
        .join(
            ObservationItem,
            and_(
                ObservationItem.owner_id == HealthObject.owner_id,
                ObservationItem.object_id == HealthObject.id,
            ),
        )
        .where(
            *owner_conditions,
            HealthObject.object_type == "observation",
            or_(
                and_(
                    ObservationItem.time_precision == "date_only",
                    ObservationItem.local_date >= from_date,
                    ObservationItem.local_date <= (as_of_local_date or to_date),
                ),
                and_(
                    ObservationItem.time_precision == "instant",
                    ObservationItem.observed_at < observation_query_end,
                    or_(
                        and_(
                            ObservationItem.interval_end.is_(None),
                            ObservationItem.observed_at >= start_at,
                        ),
                        and_(
                            ObservationItem.interval_end.is_not(None),
                            ObservationItem.interval_end > start_at,
                        ),
                    ),
                ),
            ),
        )
        .order_by(HealthObject.id)
        .limit(remaining + 1)
    )
    observation_rows = session.execute(observation_query).all()
    if len(observation_rows) > remaining:
        raise AnalyticsValidationError(
            "The selected range contains too many health records; narrow it."
        )
    events: list[EventInput] = []
    for obj, item in event_rows:
        time_point: dict[str, Any]
        if item.time_precision == "date_only":
            time_point = {
                "precision": "date_only",
                "local_date": item.local_date,
                "timezone": item.timezone,
            }
        else:
            time_point = {
                "precision": "instant",
                "occurred_at": item.occurred_at,
                "timezone": item.timezone,
            }
        try:
            ended_at = item.ended_at
            if as_of is not None and ended_at is not None and ended_at > as_of:
                ended_at = as_of
            schema = EventSchemaV1.model_validate(
                {
                    "domain": obj.domain,
                    "time": time_point,
                    "ended_at": ended_at,
                    "payload": item.payload,
                }
            )
        except ValidationError as exc:
            raise RuntimeError("stored Event schema is invalid") from exc
        events.append((obj, item, schema))
    observations: list[ObservationInput] = []
    for observation_obj, observation_item in observation_rows:
        if observation_item.time_precision == "date_only":
            observation_time_point = {
                "precision": "date_only",
                "local_date": observation_item.local_date,
                "timezone": observation_item.timezone,
            }
        else:
            observation_time_point = {
                "precision": "instant",
                "occurred_at": observation_item.observed_at,
                "timezone": observation_item.timezone,
            }
        try:
            interval_end = observation_item.interval_end
            if as_of is not None and interval_end is not None and interval_end > as_of:
                interval_end = as_of
            observation_schema = ObservationSchemaV1.model_validate(
                {
                    "domain": observation_obj.domain,
                    "time": observation_time_point,
                    "interval_end": interval_end,
                    "payload": observation_item.payload,
                }
            )
        except ValidationError as exc:
            raise RuntimeError("stored Observation schema is invalid") from exc
        observations.append((observation_obj, observation_item, observation_schema))
    links: dict[UUID, set[UUID]] = {}
    observation_ids = [obj.id for obj, _, _ in observations]
    if observation_ids:
        event_ids = [obj.id for obj, _, _ in events]
        link_conditions: list[Any] = [
            EventObservationLink.owner_id == owner_id,
            EventObservationLink.observation_object_id.in_(observation_ids),
        ]
        if event_ids:
            link_conditions.append(EventObservationLink.event_object_id.in_(event_ids))
        else:
            return events, observations, {}
        for event_id, observation_id in session.execute(
            select(
                EventObservationLink.event_object_id, EventObservationLink.observation_object_id
            ).where(*link_conditions)
        ).all():
            links.setdefault(event_id, set()).add(observation_id)
    return events, observations, links


def _tracker_metric_parts(metric: str) -> tuple[UUID, str, int] | None:
    match = _TRACKER_METRIC.fullmatch(metric)
    if not match:
        return None
    try:
        return UUID(match.group(1)), match.group(2), int(match.group(3))
    except ValueError:
        return None


def metric_definition(session: Session, owner_id: UUID, metric: str) -> MetricDefinition:
    if metric in METRIC_CATALOG:
        return METRIC_CATALOG[AnalyticsMetric(metric)]
    parts = _tracker_metric_parts(metric)
    if parts is None:
        raise AnalyticsValidationError("The selected metric is not supported.")
    tracker_id, field_id, version = parts
    row = session.execute(
        select(HealthObject, PlanningResource, TrackerSchemaVersion)
        .join(
            PlanningResource,
            and_(
                PlanningResource.owner_id == HealthObject.owner_id,
                PlanningResource.object_id == HealthObject.id,
            ),
        )
        .join(
            TrackerSchemaVersion,
            and_(
                TrackerSchemaVersion.owner_id == HealthObject.owner_id,
                TrackerSchemaVersion.tracker_id == HealthObject.id,
                TrackerSchemaVersion.version == version,
            ),
        )
        .where(
            HealthObject.owner_id == owner_id,
            HealthObject.id == tracker_id,
            HealthObject.object_type == "tracker_definition",
            PlanningResource.resource_kind == "tracker_definition",
        )
    ).one_or_none()
    if row is None:
        raise AnalyticsValidationError("The selected tracker metric is unavailable.")
    _, _, schema_row = row
    try:
        definition = TrackerDefinitionV1.model_validate(schema_row.definition)
    except ValidationError as exc:
        raise RuntimeError("stored tracker schema is invalid") from exc
    field = next((item for item in definition.fields if item.id == field_id), None)
    if field is None or field.kind not in (TrackerFieldKind.NUMBER, TrackerFieldKind.QUANTITY):
        raise AnalyticsValidationError("Only number and quantity tracker fields can be analyzed.")
    unit = field.unit.value if field.unit is not None else "value"
    return MetricDefinition(
        metric=metric,
        label=_tracker_metric_label(definition.name, field.label, version),
        unit=unit,
        aggregation="latest known tracker field value per local date; exact immutable schema version",
        minimum_known_days=5,
    )


def list_metric_definitions(session: Session, owner_id: UUID) -> list[MetricDefinition]:
    definitions = list(METRIC_CATALOG.values())
    rows = session.execute(
        select(HealthObject, TrackerSchemaVersion)
        .join(
            TrackerSchemaVersion,
            and_(
                TrackerSchemaVersion.owner_id == HealthObject.owner_id,
                TrackerSchemaVersion.tracker_id == HealthObject.id,
            ),
        )
        .where(HealthObject.owner_id == owner_id, HealthObject.object_type == "tracker_definition")
        .order_by(HealthObject.id, TrackerSchemaVersion.version)
    ).all()
    for obj, schema_row in rows:
        try:
            definition = TrackerDefinitionV1.model_validate(schema_row.definition)
        except ValidationError as exc:
            raise RuntimeError("stored tracker schema is invalid") from exc
        for field in definition.fields:
            if field.kind not in (TrackerFieldKind.NUMBER, TrackerFieldKind.QUANTITY):
                continue
            metric = f"tracker:{obj.id}:{field.id}:v{schema_row.version}"
            definitions.append(
                MetricDefinition(
                    metric=metric,
                    label=_tracker_metric_label(definition.name, field.label, schema_row.version),
                    unit=field.unit.value if field.unit is not None else "value",
                    aggregation="latest known tracker field value per local date; exact immutable schema version",
                    minimum_known_days=5,
                )
            )
    return definitions


def _tracker_metric_label(name: str, field_label: str, version: int) -> str:
    suffix = f" (schema v{version})"
    prefix = f"{name} · {field_label}"
    max_prefix = 80 - len(suffix)
    if len(prefix) > max_prefix:
        prefix = prefix[: max_prefix - 1].rstrip() + "…"
    return prefix + suffix


def _event_metric_rows(metric: str, events: list[EventInput]) -> list[EventInput]:
    domain, _ = _EVENT_METRICS[metric]
    if metric in {"symptom_severity", "symptom_episode_count"}:
        return [row for row in events if row[2].domain == DailyDomain.SYMPTOMS]
    return [row for row in events if row[2].domain == domain]


def _observation_metric_rows(
    metric: str, observations: list[ObservationInput]
) -> list[ObservationInput]:
    _, wanted = _EVENT_METRICS[metric]
    return [row for row in observations if row[2].payload.value.metric == wanted]


def _evidence_refs(
    events: list[EventInput], observations: list[ObservationInput]
) -> list[EvidenceReference]:
    refs = [
        EvidenceReference(object_id=obj.id, revision=obj.revision, object_type="event")
        for obj, _, _ in events
    ]
    refs.extend(
        EvidenceReference(object_id=obj.id, revision=obj.revision, object_type="observation")
        for obj, _, _ in observations
    )
    return sorted(refs, key=lambda ref: (str(ref.object_id), ref.revision))


def _tracker_points(
    metric: str,
    definition: MetricDefinition,
    observations: list[ObservationInput],
    from_date: date,
    to_date: date,
    timezone: str,
) -> tuple[list[DailyMetricPoint], list[EvidenceReference]]:
    parts = _tracker_metric_parts(metric)
    if parts is None:
        raise AnalyticsValidationError("The selected metric is not supported.")
    tracker_id, field_id, version = parts
    rows = [
        row
        for row in observations
        if row[1].tracker_id == tracker_id and row[1].tracker_schema_version == version
    ]
    refs = _evidence_refs([], rows)
    points: list[DailyMetricPoint] = []
    current = from_date
    while current <= to_date:
        day_rows: list[tuple[ObservationInput, float | None]] = []
        for row in rows:
            _, item, schema = row
            if not _row_date_in_range(
                item.time_precision,
                item.local_date,
                item.observed_at,
                item.interval_end,
                current,
                current,
                timezone,
            ):
                continue
            value = schema.payload.value
            extracted: float | None = None
            if isinstance(value, CustomTrackerValueV1) and field_id in value.values:
                raw = value.values[field_id]
                if isinstance(raw, bool):
                    extracted = None
                elif isinstance(raw, (int, float)):
                    extracted = float(raw)
                elif (
                    isinstance(raw, dict)
                    and set(raw) == {"value", "unit"}
                    and raw["unit"] == definition.unit
                    and isinstance(raw["value"], (int, float))
                    and not isinstance(raw["value"], bool)
                ):
                    extracted = float(raw["value"])
            if extracted is not None:
                day_rows.append((row, extracted))
        day_rows.sort(
            key=lambda value: (
                value[0][2].time.local_date
                if value[0][2].time.precision == "date_only"
                else value[0][2].time.occurred_at.astimezone(ZoneInfo(timezone)).date(),
                0 if value[0][2].time.precision == "date_only" else 1,
                datetime.min.replace(tzinfo=UTC)
                if value[0][2].time.precision == "date_only"
                else value[0][2].time.occurred_at.astimezone(UTC),
                str(value[0][0].id),
            )
        )
        all_rows_count = sum(
            1
            for row in rows
            if _row_date_in_range(
                row[1].time_precision,
                row[1].local_date,
                row[1].observed_at,
                row[1].interval_end,
                current,
                current,
                timezone,
            )
        )
        known = len(day_rows)
        points.append(
            DailyMetricPoint(
                date=current,
                value=day_rows[-1][1] if day_rows else None,
                logged_count=all_rows_count,
                known_count=known,
                total_count=all_rows_count,
                partial=known < all_rows_count,
            )
        )
        current += timedelta(days=1)
    return points, refs


def _standard_points(
    metric: str,
    events: list[EventInput],
    observations: list[ObservationInput],
    links: dict[UUID, set[UUID]],
    from_date: date,
    to_date: date,
    timezone: str,
) -> tuple[list[DailyMetricPoint], list[EvidenceReference]]:
    relevant_events = _event_metric_rows(metric, events)
    relevant_observations = _observation_metric_rows(metric, observations)
    full_events = [(obj.id, schema) for obj, _, schema in events]
    full_observations = [(obj.id, schema) for obj, _, schema in observations]

    def local_day(schema: EventSchemaV1 | ObservationSchemaV1) -> date:
        time = schema.time
        return (
            time.local_date
            if time.precision == "date_only"
            else time.occurred_at.astimezone(ZoneInfo(timezone)).date()
        )

    eligible_symptom_events = {
        object_id: local_day(schema)
        for object_id, schema in full_events
        if schema.domain == DailyDomain.SYMPTOMS and schema.payload.kind == "symptom"
    }
    observations_by_id = {object_id: schema for object_id, schema in full_observations}
    eligible_severity_ids: set[UUID] = set()
    for event_id, observation_ids in links.items():
        event_day = eligible_symptom_events.get(event_id)
        if event_day is None:
            continue
        for observation_id in observation_ids:
            observation = observations_by_id.get(observation_id)
            if (
                observation is not None
                and observation.payload.value.metric == MetricKey.SYMPTOM_SEVERITY
                and local_day(observation) == event_day
            ):
                eligible_severity_ids.add(observation_id)
    full_observations = [
        row
        for row in full_observations
        if row[1].payload.value.metric != MetricKey.SYMPTOM_SEVERITY
        or row[0] in eligible_severity_ids
    ]
    if metric == "symptom_severity":
        eligible_ids = {object_id for object_id in eligible_severity_ids}
        relevant_observations = [row for row in relevant_observations if row[0].id in eligible_ids]
    elif metric == "symptom_episode_count":
        relevant_observations = []
    refs = _evidence_refs(relevant_events, relevant_observations)
    wanted_domain, wanted_metric = _EVENT_METRICS[metric]
    points: list[DailyMetricPoint] = []
    current = from_date
    while current <= to_date:
        summaries = summarize_today(full_events, full_observations, current, timezone)
        summary = next(
            (
                row
                for row in summaries
                if row.domain == wanted_domain and row.metric == wanted_metric
            ),
            None,
        )
        if summary is None:
            raise RuntimeError("daily metric catalog is missing a supported summary")
        points.append(
            DailyMetricPoint(
                date=current,
                value=summary.known_value,
                logged_count=summary.logged_count,
                known_count=summary.coverage.known_count,
                total_count=summary.coverage.total_count,
                partial=summary.partial,
            )
        )
        current += timedelta(days=1)
    return points, refs


def _series_from_inputs(
    metric: str,
    definition: MetricDefinition,
    from_date: date,
    to_date: date,
    timezone: str,
    generation: int,
    events: list[EventInput],
    observations: list[ObservationInput],
    links: dict[UUID, set[UUID]],
) -> MetricSeries:
    if _tracker_metric_parts(metric) is not None:
        points, refs = _tracker_points(
            metric, definition, observations, from_date, to_date, timezone
        )
    else:
        points, refs = _standard_points(
            metric, events, observations, links, from_date, to_date, timezone
        )
    return definition, points, refs, generation


def _series(
    session: Session,
    owner_id: UUID,
    metric: str,
    from_date: date,
    to_date: date,
    timezone: str,
    *,
    ai_permitted_only: bool = False,
    excluded_object_ids: set[UUID] | None = None,
    as_of: datetime | None = None,
) -> MetricSeries:
    generation = session.scalar(
        select(User.daily_sequence).where(User.id == owner_id, User.lifecycle == "active")
    )
    if generation is None:
        raise AnalyticsNotFound
    definition = metric_definition(session, owner_id, metric)
    events, observations, links = _load_inputs(
        session,
        owner_id,
        from_date,
        to_date,
        timezone,
        ai_permitted_only=ai_permitted_only,
        excluded_object_ids=excluded_object_ids,
        as_of=as_of,
    )
    return _series_from_inputs(
        metric,
        definition,
        from_date,
        to_date,
        timezone,
        generation,
        events,
        observations,
        links,
    )


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
        generation = session.scalar(
            select(User.daily_sequence).where(User.id == owner_id, User.lifecycle == "active")
        )
        if generation is None:
            raise AnalyticsNotFound
        events, observations, links = _load_inputs(session, owner_id, from_date, to_date, timezone)
        series_by_metric = {
            metric: _series_from_inputs(
                metric,
                metric_definition(session, owner_id, metric),
                from_date,
                to_date,
                timezone,
                generation,
                events,
                observations,
                links,
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
                return prior_state
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
    generation = session.scalar(
        select(User.daily_sequence).where(User.id == owner_id, User.lifecycle == "active")
    )
    if generation is None:
        raise AnalyticsNotFound
    events, observations, links = _load_inputs(session, owner_id, from_date, to_date, timezone)
    prepared_series = {
        metric: _series_from_inputs(
            metric,
            metric_definition(session, owner_id, metric),
            from_date,
            to_date,
            timezone,
            generation,
            events,
            observations,
            links,
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
