"""Owner-scoped, bounded analytics source reads and metric definitions."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from health_api.application.analytics_computation import (
    _series_from_snapshot,
    _tracker_metric_label,
    _tracker_metric_parts,
)
from health_api.application.analytics_contracts import (
    AnalyticsNotFound,
    AnalyticsSourceSnapshot,
    AnalyticsValidationError,
    EventInput,
    MetricSeries,
    ObservationInput,
)
from health_api.application.today_service import (
    healthkit_preferred_installations,
)
from health_api.domain.analytics import (
    MAX_ANALYSIS_DAYS,
    MAX_ANALYSIS_ROWS,
    METRIC_CATALOG,
    AnalyticsMetric,
    MetricDefinition,
)
from health_api.domain.daily import local_day_bounds
from health_api.domain.daily_rollups import DailyProvenance
from health_api.domain.planning import TrackerDefinitionV1, TrackerFieldKind
from health_api.domain.schemas import (
    EventSchemaV1,
    ObservationSchemaV1,
)
from health_api.persistence.models import (
    EventItem,
    EventObservationLink,
    HealthObject,
    ObservationItem,
    PlanningResource,
    Source,
    TrackerSchemaVersion,
    User,
)
from pydantic import ValidationError
from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session

ANALYTICS_QUERY_TIMEOUT_MS = 2_000


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
) -> tuple[
    list[EventInput],
    list[ObservationInput],
    dict[UUID, set[UUID]],
    dict[UUID, DailyProvenance],
]:
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
        select(HealthObject, EventItem, Source.source_kind)
        .join(
            EventItem,
            and_(
                EventItem.owner_id == HealthObject.owner_id, EventItem.object_id == HealthObject.id
            ),
        )
        .join(
            Source,
            and_(Source.owner_id == HealthObject.owner_id, Source.id == HealthObject.source_id),
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
        select(HealthObject, ObservationItem, Source.source_kind)
        .join(
            ObservationItem,
            and_(
                ObservationItem.owner_id == HealthObject.owner_id,
                ObservationItem.object_id == HealthObject.id,
            ),
        )
        .join(
            Source,
            and_(Source.owner_id == HealthObject.owner_id, Source.id == HealthObject.source_id),
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
    provenance: dict[UUID, DailyProvenance] = {}
    for obj, item, source_kind in event_rows:
        provenance[obj.id] = DailyProvenance(
            source_kind=source_kind,
            confirmation_status=obj.confirmation_status,
            metadata=obj.metadata_json,
            revision=obj.revision,
        )
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
    for observation_obj, observation_item, source_kind in observation_rows:
        provenance[observation_obj.id] = DailyProvenance(
            source_kind=source_kind,
            confirmation_status=observation_obj.confirmation_status,
            metadata=observation_obj.metadata_json,
            revision=observation_obj.revision,
        )
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
            return events, observations, {}, provenance
        for event_id, observation_id in session.execute(
            select(
                EventObservationLink.event_object_id, EventObservationLink.observation_object_id
            ).where(*link_conditions)
        ).all():
            links.setdefault(event_id, set()).add(observation_id)
    return events, observations, links, provenance


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
    generation = _active_owner_generation(session, owner_id)
    definition = metric_definition(session, owner_id, metric)
    snapshot = load_analytics_snapshot(
        session,
        owner_id,
        from_date,
        to_date,
        timezone,
        ai_permitted_only=ai_permitted_only,
        excluded_object_ids=excluded_object_ids,
        as_of=as_of,
        generation=generation,
    )
    return _series_from_snapshot(
        metric,
        definition,
        from_date,
        to_date,
        timezone,
        snapshot,
    )


def load_analytics_snapshot(
    session: Session,
    owner_id: UUID,
    from_date: date,
    to_date: date,
    timezone: str,
    *,
    ai_permitted_only: bool = False,
    excluded_object_ids: set[UUID] | None = None,
    as_of: datetime | None = None,
    generation: int | None = None,
) -> AnalyticsSourceSnapshot:
    """Load one bounded owner snapshot and capture its generation marker.

    Computation can use this snapshot after the read transaction ends. Every
    artifact write must still revalidate the captured generation and evidence.
    """
    if generation is None:
        generation = _active_owner_generation(session, owner_id)
    events, observations, links, provenance = _load_inputs(
        session,
        owner_id,
        from_date,
        to_date,
        timezone,
        ai_permitted_only=ai_permitted_only,
        excluded_object_ids=excluded_object_ids,
        as_of=as_of,
    )
    return AnalyticsSourceSnapshot(
        generation=generation,
        events=events,
        observations=observations,
        links=links,
        provenance=provenance,
        preferred_installations=healthkit_preferred_installations(session, owner_id),
    )


def _active_owner_generation(session: Session, owner_id: UUID) -> int:
    generation = session.scalar(
        select(User.daily_sequence).where(User.id == owner_id, User.lifecycle == "active")
    )
    if generation is None:
        raise AnalyticsNotFound
    return generation
