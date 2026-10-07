"""Owner-scoped daily object writes, history, and atomic Event/Observation links."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, TypeGuard
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from health_api.application.analytics_service import invalidate_analytics
from health_api.application.envelope_service import manual_source, next_daily_sequence, unit_of_work
from health_api.application.errors import DailyConflict, DailyNotFound, DailyValidationError
from health_api.domain.daily import local_day_bounds
from health_api.domain.planning import TrackerDefinitionV1, validate_tracker_values
from health_api.domain.schemas import (
    CustomTrackerValueV1,
    DailyDomain,
    EventKind,
    EventPayloadSchemaV1,
    EventSchemaV1,
    InstantTimePoint,
    MetricKey,
    ObservationPayloadV1,
    ObservationSchemaV1,
    ProfileSchemaRegistry,
)
from health_api.persistence.models import (
    EventItem,
    EventObservationLink,
    HealthKitImportIdentity,
    HealthObject,
    HealthObjectRevision,
    ObservationItem,
    PlanningResource,
    Source,
    TrackerSchemaVersion,
    User,
)

type EventAggregate = tuple[HealthObject, EventItem, Source, tuple[UUID, ...]]
type ObservationAggregate = tuple[HealthObject, ObservationItem, Source]
type DailyAggregate = EventAggregate | ObservationAggregate


def _is_event_aggregate(value: DailyAggregate) -> TypeGuard[EventAggregate]:
    return isinstance(value[1], EventItem)


def _is_observation_aggregate(value: DailyAggregate) -> TypeGuard[ObservationAggregate]:
    return isinstance(value[1], ObservationItem)


@dataclass(frozen=True)
class CreateDailyEvent:
    id: UUID
    event: EventSchemaV1
    ai_use_allowed: bool = False
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class CreateDailyObservation:
    id: UUID
    observation: ObservationSchemaV1
    ai_use_allowed: bool = False
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class CreateDailyLink:
    event_id: UUID
    observation_id: UUID
    role: str = "symptom_severity"


@dataclass(frozen=True)
class CreateDailyEntry:
    events: tuple[CreateDailyEvent, ...] = ()
    observations: tuple[CreateDailyObservation, ...] = ()
    links: tuple[CreateDailyLink, ...] = ()


@dataclass(frozen=True)
class CreateDailyEntryResult:
    events: tuple[EventAggregate, ...]
    observations: tuple[ObservationAggregate, ...]
    created: bool


type DailyRecord = EventSchemaV1 | ObservationSchemaV1


def _canonical_content(record_type: str, record: DailyRecord, ai_use_allowed: bool) -> str:
    return json.dumps(
        {
            "object_type": record_type,
            "record": record.model_dump(mode="json"),
            "ai_use_allowed": ai_use_allowed,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _fingerprint(record_type: str, record: DailyRecord, ai_use_allowed: bool) -> str:
    return hashlib.sha256(
        _canonical_content(record_type, record, ai_use_allowed).encode("utf-8")
    ).hexdigest()


def _legacy_fingerprint(record_type: str, record: DailyRecord) -> str:
    """Preserve uncertain retries created before daily AI permission was added."""
    legacy_content = json.dumps(
        {"object_type": record_type, "record": record.model_dump(mode="json")},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(legacy_content.encode("utf-8")).hexdigest()


def _event_fields(schema: EventSchemaV1) -> dict[str, Any]:
    time_point = schema.time
    return {
        "event_kind": schema.payload.kind.value,
        "time_precision": time_point.precision,
        "occurred_at": time_point.occurred_at if isinstance(time_point, InstantTimePoint) else None,
        "local_date": time_point.local_date
        if not isinstance(time_point, InstantTimePoint)
        else None,
        "timezone": time_point.timezone,
        "ended_at": schema.ended_at,
        "payload": schema.payload.model_dump(mode="json"),
    }


def _observation_fields(schema: ObservationSchemaV1) -> dict[str, Any]:
    time_point = schema.time
    value = schema.payload.value
    fields: dict[str, Any] = {
        "time_precision": time_point.precision,
        "observed_at": time_point.occurred_at if isinstance(time_point, InstantTimePoint) else None,
        "local_date": time_point.local_date
        if not isinstance(time_point, InstantTimePoint)
        else None,
        "timezone": time_point.timezone,
        "interval_end": schema.interval_end,
        "payload": schema.payload.model_dump(mode="json"),
    }
    if isinstance(value, CustomTrackerValueV1):
        fields.update(
            {
                "metric_key": "custom",
                "numeric_value": None,
                "unit": "custom",
                "tracker_id": value.tracker_id,
                "tracker_schema_version": value.schema_version,
                "tracker_values": value.values,
            }
        )
    else:
        fields.update(
            {
                "metric_key": value.metric.value,
                "numeric_value": float(value.value),
                "unit": value.unit.value,
                "tracker_id": None,
                "tracker_schema_version": None,
                "tracker_values": None,
            }
        )
    return fields


def _validate_tracker_observation(
    session: Session, owner_id: UUID, schema: ObservationSchemaV1, *, allow_archived: bool = False
) -> None:
    value = schema.payload.value
    if not isinstance(value, CustomTrackerValueV1):
        return
    row = session.execute(
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
            HealthObject.id == value.tracker_id,
            HealthObject.object_type == "tracker_definition",
        )
        .with_for_update()
    ).one_or_none()
    if row is None:
        raise DailyNotFound
    tracker, resource = row
    if not allow_archived and (tracker.status != "active" or resource.lifecycle != "active"):
        raise DailyValidationError("archived trackers do not accept new entries")
    schema_version = session.get(
        TrackerSchemaVersion, (owner_id, value.tracker_id, value.schema_version)
    )
    if schema_version is None:
        raise DailyNotFound
    try:
        definition = TrackerDefinitionV1.model_validate(schema_version.definition)
        values = validate_tracker_values(definition, value.values)
    except (ValidationError, ValueError) as exc:
        raise DailyValidationError(
            "tracker values do not match the selected schema version"
        ) from exc
    if definition.domain != schema.domain:
        raise DailyValidationError("tracker domain does not match the Observation")
    value.values = values


def _validate_compound(command: CreateDailyEntry) -> None:
    total = len(command.events) + len(command.observations)
    if not total or total > 20:
        raise DailyValidationError("a daily entry must contain between one and twenty objects")
    ids = [entry.id for entry in command.events] + [entry.id for entry in command.observations]
    if len(set(ids)) != len(ids):
        raise DailyValidationError("daily entry object IDs must be unique")
    event_by_id = {entry.id: entry.event for entry in command.events}
    observation_by_id = {entry.id: entry.observation for entry in command.observations}
    link_keys = [(link.event_id, link.observation_id, link.role) for link in command.links]
    event_role_keys = [(link.event_id, link.role) for link in command.links]
    observation_role_keys = [(link.observation_id, link.role) for link in command.links]
    if (
        len(command.links) > 20
        or len(set(link_keys)) != len(link_keys)
        or len(set(event_role_keys)) != len(event_role_keys)
        or len(set(observation_role_keys)) != len(observation_role_keys)
    ):
        raise DailyValidationError("daily entry links are duplicated or exceed the limit")
    linked_observation_ids: set[UUID] = set()
    for link in command.links:
        event = event_by_id.get(link.event_id)
        observation = observation_by_id.get(link.observation_id)
        if event is None or observation is None:
            raise DailyValidationError("linked objects must be in the same atomic save")
        if link.role != "symptom_severity":
            raise DailyValidationError("unsupported daily relationship")
        if event.domain != DailyDomain.SYMPTOMS or event.payload.kind != EventKind.SYMPTOM:
            raise DailyValidationError("symptom severity must link to a symptom Event")
        if (
            observation.domain != DailyDomain.SYMPTOMS
            or observation.payload.value.metric != MetricKey.SYMPTOM_SEVERITY
        ):
            raise DailyValidationError("symptom severity must link to a severity Observation")
        linked_observation_ids.add(link.observation_id)
    for observation_id, observation in observation_by_id.items():
        if (
            observation.payload.value.metric == MetricKey.SYMPTOM_SEVERITY
            and observation_id not in linked_observation_ids
        ):
            raise DailyValidationError("symptom severity Observation requires a symptom Event")


def _manual_create_object(
    *,
    owner_id: UUID,
    object_id: UUID,
    object_type: str,
    domain: DailyDomain,
    title: str,
    notes: str | None,
    source: Source,
    fingerprint: str,
    ai_use_allowed: bool = False,
    metadata: dict[str, Any] | None = None,
) -> HealthObject:
    return HealthObject(
        id=object_id,
        owner_id=owner_id,
        object_type=object_type,
        domain=domain.value,
        status="active",
        title=title,
        source_id=source.id,
        confirmation_status="unconfirmed" if source.source_kind == "device" else "user_confirmed",
        schema_version=1,
        revision=1,
        notes=notes,
        metadata_json=metadata or {},
        ai_use_allowed=ai_use_allowed,
        cross_domain_use_allowed=False,
        create_fingerprint=fingerprint,
    )


def _snapshot_common(obj: HealthObject, source: Source) -> dict[str, Any]:
    return {
        "id": str(obj.id),
        "object_type": obj.object_type,
        "domain": obj.domain,
        "status": obj.status,
        "title": obj.title,
        "valid_from": obj.valid_from.isoformat() if obj.valid_from else None,
        "valid_to": obj.valid_to.isoformat() if obj.valid_to else None,
        "recorded_at": obj.recorded_at.isoformat(),
        "created_at": obj.created_at.isoformat(),
        "updated_at": obj.updated_at.isoformat(),
        "source": {"id": str(source.id), "kind": source.source_kind, "name": source.display_name},
        "confirmation_status": obj.confirmation_status,
        "schema_version": obj.schema_version,
        "revision": obj.revision,
        "notes": obj.notes,
        "metadata": obj.metadata_json,
        "permissions": {
            "ai_use_allowed": obj.ai_use_allowed,
            "cross_domain_use_allowed": obj.cross_domain_use_allowed,
        },
    }


def _append_event_revision(
    session: Session,
    owner_id: UUID,
    obj: HealthObject,
    event: EventItem,
    source: Source,
    linked_observation_ids: tuple[UUID, ...],
    daily_sequence: int,
    reason: str,
    proposal_id: UUID | None = None,
) -> None:
    time_point: dict[str, Any] = {"precision": event.time_precision, "timezone": event.timezone}
    if event.time_precision == "instant":
        time_point["occurred_at"] = event.occurred_at.isoformat() if event.occurred_at else None
    else:
        time_point["local_date"] = event.local_date.isoformat() if event.local_date else None
    snapshot = {
        **_snapshot_common(obj, source),
        "time": time_point,
        "ended_at": event.ended_at.isoformat() if event.ended_at else None,
        "payload": event.payload,
        "linked_observation_ids": [str(item) for item in linked_observation_ids],
    }
    session.add(
        HealthObjectRevision(
            owner_id=owner_id,
            object_id=obj.id,
            revision=obj.revision,
            actor_kind="user",
            actor_id=owner_id,
            reason=reason,
            proposal_id=proposal_id,
            snapshot=snapshot,
            daily_sequence=daily_sequence,
            daily_object_type="event",
            daily_domain=obj.domain,
            daily_status=obj.status,
            daily_time_precision=event.time_precision,
            daily_occurred_at=event.occurred_at,
            daily_local_date=event.local_date,
            daily_ended_at=event.ended_at,
        )
    )


def _append_observation_revision(
    session: Session,
    owner_id: UUID,
    obj: HealthObject,
    observation: ObservationItem,
    source: Source,
    daily_sequence: int,
    reason: str,
    proposal_id: UUID | None = None,
) -> None:
    time_point: dict[str, Any] = {
        "precision": observation.time_precision,
        "timezone": observation.timezone,
    }
    if observation.time_precision == "instant":
        time_point["occurred_at"] = (
            observation.observed_at.isoformat() if observation.observed_at else None
        )
    else:
        time_point["local_date"] = (
            observation.local_date.isoformat() if observation.local_date else None
        )
    snapshot = {
        **_snapshot_common(obj, source),
        "time": time_point,
        "interval_end": observation.interval_end.isoformat() if observation.interval_end else None,
        "payload": observation.payload,
    }
    session.add(
        HealthObjectRevision(
            owner_id=owner_id,
            object_id=obj.id,
            revision=obj.revision,
            actor_kind="user",
            actor_id=owner_id,
            reason=reason,
            proposal_id=proposal_id,
            snapshot=snapshot,
            daily_sequence=daily_sequence,
            daily_object_type="observation",
            daily_domain=obj.domain,
            daily_status=obj.status,
            daily_time_precision=observation.time_precision,
            daily_occurred_at=observation.observed_at,
            daily_local_date=observation.local_date,
            daily_ended_at=observation.interval_end,
        )
    )


def _event_aggregate(session: Session, owner_id: UUID, object_id: UUID) -> EventAggregate | None:
    statement = (
        select(HealthObject, EventItem, Source)
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
        .where(HealthObject.owner_id == owner_id, HealthObject.id == object_id)
    )
    row = session.execute(statement).one_or_none()
    if row is None:
        return None
    linked_ids = tuple(
        session.scalars(
            select(EventObservationLink.observation_object_id)
            .where(
                EventObservationLink.owner_id == owner_id,
                EventObservationLink.event_object_id == object_id,
            )
            .order_by(EventObservationLink.observation_object_id)
        )
    )
    return row[0], row[1], row[2], linked_ids


def _observation_aggregate(
    session: Session, owner_id: UUID, object_id: UUID
) -> ObservationAggregate | None:
    statement = (
        select(HealthObject, ObservationItem, Source)
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
        .where(HealthObject.owner_id == owner_id, HealthObject.id == object_id)
    )
    row = session.execute(statement).one_or_none()
    if row is None:
        return None
    return row[0], row[1], row[2]


def _daily_aggregate(session: Session, owner_id: UUID, object_id: UUID) -> DailyAggregate:
    obj = session.scalar(
        select(HealthObject).where(HealthObject.owner_id == owner_id, HealthObject.id == object_id)
    )
    if obj is None:
        raise DailyNotFound
    aggregate = (
        _event_aggregate(session, owner_id, object_id)
        if obj.object_type == "event"
        else _observation_aggregate(session, owner_id, object_id)
    )
    if aggregate is None:
        raise RuntimeError("daily object envelope has no matching subtype")
    return aggregate


def get_daily_item(session: Session, owner_id: UUID, object_id: UUID) -> DailyAggregate:
    return _daily_aggregate(session, owner_id, object_id)


def list_daily_items(
    session: Session,
    owner_id: UUID,
    object_type: str,
    limit: int,
    after: tuple[datetime, UUID] | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    timezone: str | None = None,
) -> list[DailyAggregate]:
    if (from_date is None) != (to_date is None):
        raise ValueError("both date range bounds are required")
    conditions = [
        HealthObject.owner_id == owner_id,
        HealthObject.object_type == object_type,
        HealthObject.status == "active",
    ]
    if after is not None:
        conditions.append(
            or_(
                HealthObject.created_at < after[0],
                and_(HealthObject.created_at == after[0], HealthObject.id < after[1]),
            )
        )
    if from_date is not None and to_date is not None:
        if timezone is None or to_date < from_date or to_date == date.max:
            raise ValueError("daily list date range is invalid")
        start_at = local_day_bounds(from_date, timezone)[0]
        end_at = local_day_bounds(to_date + timedelta(days=1), timezone)[0]
        if object_type == "event":
            time_filter = or_(
                and_(
                    EventItem.time_precision == "instant",
                    EventItem.occurred_at < end_at,
                    or_(
                        and_(EventItem.ended_at.is_(None), EventItem.occurred_at >= start_at),
                        EventItem.ended_at > start_at,
                    ),
                ),
                and_(
                    EventItem.time_precision == "date_only",
                    EventItem.local_date >= from_date,
                    EventItem.local_date <= to_date,
                ),
            )
        elif object_type == "observation":
            time_filter = or_(
                and_(
                    ObservationItem.time_precision == "instant",
                    ObservationItem.observed_at < end_at,
                    or_(
                        and_(
                            ObservationItem.interval_end.is_(None),
                            ObservationItem.observed_at >= start_at,
                        ),
                        ObservationItem.interval_end > start_at,
                    ),
                ),
                and_(
                    ObservationItem.time_precision == "date_only",
                    ObservationItem.local_date >= from_date,
                    ObservationItem.local_date <= to_date,
                ),
            )
        else:
            raise ValueError("unsupported daily object type")
        conditions.append(time_filter)

    order_by = (HealthObject.created_at.desc(), HealthObject.id.desc())
    if object_type == "event":
        event_rows = session.execute(
            select(HealthObject, EventItem, Source)
            .join(
                EventItem,
                and_(
                    EventItem.owner_id == HealthObject.owner_id,
                    EventItem.object_id == HealthObject.id,
                ),
            )
            .join(
                Source,
                and_(Source.owner_id == HealthObject.owner_id, Source.id == HealthObject.source_id),
            )
            .where(*conditions)
            .order_by(*order_by)
            .limit(limit)
        ).all()
        event_ids = {row[0].id for row in event_rows}
        link_rows = (
            session.execute(
                select(
                    EventObservationLink.event_object_id,
                    EventObservationLink.observation_object_id,
                )
                .where(
                    EventObservationLink.owner_id == owner_id,
                    EventObservationLink.event_object_id.in_(event_ids),
                )
                .order_by(EventObservationLink.observation_object_id)
            ).all()
            if event_ids
            else []
        )
        links_by_event: dict[UUID, list[UUID]] = {}
        for event_id, observation_id in link_rows:
            links_by_event.setdefault(event_id, []).append(observation_id)
        return [
            (obj, event, source, tuple(links_by_event.get(obj.id, [])))
            for obj, event, source in event_rows
        ]
    if object_type == "observation":
        observation_rows = session.execute(
            select(HealthObject, ObservationItem, Source)
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
            .where(*conditions)
            .order_by(*order_by)
            .limit(limit)
        ).all()
        return [(obj, observation, source) for obj, observation, source in observation_rows]
    raise ValueError("unsupported daily object type")


def _requested_ids(command: CreateDailyEntry) -> set[UUID]:
    return {entry.id for entry in command.events} | {entry.id for entry in command.observations}


def create_daily_entry(
    session: Session,
    owner_id: UUID,
    command: CreateDailyEntry,
    *,
    write_source: Source | None = None,
    proposal_id: UUID | None = None,
) -> CreateDailyEntryResult:
    _validate_compound(command)
    object_ids = _requested_ids(command)
    event_ids = {entry.id for entry in command.events}
    expected_fingerprints = {
        entry.id: _fingerprint("event", entry.event, entry.ai_use_allowed)
        for entry in command.events
    } | {
        entry.id: _fingerprint("observation", entry.observation, entry.ai_use_allowed)
        for entry in command.observations
    }
    legacy_fingerprints = {
        entry.id: _legacy_fingerprint("event", entry.event)
        for entry in command.events
        if not entry.ai_use_allowed
    } | {
        entry.id: _legacy_fingerprint("observation", entry.observation)
        for entry in command.observations
        if not entry.ai_use_allowed
    }
    try:
        with unit_of_work(session):
            owner = session.scalar(select(User).where(User.id == owner_id).with_for_update())
            if owner is None or owner.lifecycle != "active":
                raise DailyNotFound("owner does not exist")
            existing = list(
                session.scalars(
                    select(HealthObject).where(
                        HealthObject.owner_id == owner_id, HealthObject.id.in_(object_ids)
                    )
                )
            )
            if existing:
                by_id = {obj.id: obj for obj in existing}
                if set(by_id) != object_ids or any(
                    by_id[object_id].create_fingerprint
                    not in {fingerprint, legacy_fingerprints.get(object_id)}
                    or by_id[object_id].object_type
                    != ("event" if object_id in event_ids else "observation")
                    for object_id, fingerprint in expected_fingerprints.items()
                ):
                    raise DailyConflict("one or more IDs were already used for different content")
                expected_links = {
                    (link.event_id, link.observation_id, link.role) for link in command.links
                }
                existing_links = set(
                    session.execute(
                        select(
                            EventObservationLink.event_object_id,
                            EventObservationLink.observation_object_id,
                            EventObservationLink.role,
                        ).where(
                            EventObservationLink.owner_id == owner_id,
                            EventObservationLink.event_object_id.in_(
                                {entry.id for entry in command.events}
                            ),
                        )
                    ).all()
                )
                if expected_links != existing_links:
                    raise DailyConflict("the original compound save used different links")
                event_results = tuple(
                    _event_aggregate(session, owner_id, entry.id) for entry in command.events
                )
                observation_results = tuple(
                    _observation_aggregate(session, owner_id, entry.id)
                    for entry in command.observations
                )
                if any(item is None for item in (*event_results, *observation_results)):
                    raise RuntimeError("daily retry is missing a subtype row")
                return CreateDailyEntryResult(
                    events=event_results,  # type: ignore[arg-type]
                    observations=observation_results,  # type: ignore[arg-type]
                    created=False,
                )

            source = write_source or manual_source(session, owner_id)
            # All objects in this command become visible at one commit boundary.
            sequence = next_daily_sequence(session, owner_id)
            event_objects: dict[UUID, tuple[HealthObject, EventItem, int]] = {}
            observation_objects: dict[UUID, tuple[HealthObject, ObservationItem, int]] = {}
            for event_entry in command.events:
                event_schema = event_entry.event
                try:
                    validated = ProfileSchemaRegistry.validate(
                        "event", 1, event_schema.payload.model_dump(mode="json")
                    )
                except ValidationError as exc:
                    raise DailyValidationError("Event payload is invalid") from exc
                if not isinstance(validated, EventPayloadSchemaV1):
                    raise TypeError("Event registry returned an incompatible payload type")
                payload = validated.root.model_dump(mode="json")
                obj = _manual_create_object(
                    owner_id=owner_id,
                    object_id=event_entry.id,
                    object_type="event",
                    domain=event_schema.domain,
                    title=event_schema.payload.label,
                    notes=event_schema.notes,
                    source=source,
                    fingerprint=expected_fingerprints[event_entry.id],
                    ai_use_allowed=event_entry.ai_use_allowed,
                    metadata=event_entry.metadata,
                )
                event_subtype = EventItem(
                    owner_id=owner_id,
                    object_id=event_entry.id,
                    **{**_event_fields(event_schema), "payload": payload},
                )
                session.add_all([obj, event_subtype])
                event_objects[event_entry.id] = (obj, event_subtype, sequence)

            for observation_entry in command.observations:
                observation_schema = observation_entry.observation
                _validate_tracker_observation(session, owner_id, observation_schema)
                try:
                    validated = ProfileSchemaRegistry.validate(
                        "observation", 1, observation_schema.payload.model_dump(mode="json")
                    )
                except ValidationError as exc:
                    raise DailyValidationError("Observation payload is invalid") from exc
                if not isinstance(validated, ObservationPayloadV1):
                    raise TypeError("Observation registry returned an incompatible payload type")
                payload = validated.model_dump(mode="json")
                obj = _manual_create_object(
                    owner_id=owner_id,
                    object_id=observation_entry.id,
                    object_type="observation",
                    domain=observation_schema.domain,
                    title=(
                        "Custom tracker entry"
                        if isinstance(observation_schema.payload.value, CustomTrackerValueV1)
                        else observation_schema.payload.value.metric.value.replace("_", " ").title()
                    ),
                    notes=observation_schema.notes,
                    source=source,
                    fingerprint=expected_fingerprints[observation_entry.id],
                    ai_use_allowed=observation_entry.ai_use_allowed,
                    metadata=observation_entry.metadata,
                )
                observation_subtype = ObservationItem(
                    owner_id=owner_id,
                    object_id=observation_entry.id,
                    **_observation_fields(observation_schema),
                )
                session.add_all([obj, observation_subtype])
                observation_objects[observation_entry.id] = (obj, observation_subtype, sequence)

            session.flush()
            for link in command.links:
                session.add(
                    EventObservationLink(
                        owner_id=owner_id,
                        event_object_id=link.event_id,
                        observation_object_id=link.observation_id,
                        role=link.role,
                    )
                )
            session.flush()

            links_by_event: dict[UUID, list[UUID]] = {}
            for link in command.links:
                links_by_event.setdefault(link.event_id, []).append(link.observation_id)
            for event_entry in command.events:
                obj, event_subtype, sequence = event_objects[event_entry.id]
                _append_event_revision(
                    session,
                    owner_id,
                    obj,
                    event_subtype,
                    source,
                    tuple(sorted(links_by_event.get(event_entry.id, []))),
                    sequence,
                    "create",
                    proposal_id,
                )
            for observation_entry in command.observations:
                obj, observation_subtype, sequence = observation_objects[observation_entry.id]
                _append_observation_revision(
                    session,
                    owner_id,
                    obj,
                    observation_subtype,
                    source,
                    sequence,
                    "create",
                    proposal_id,
                )
            session.flush()
            event_results = tuple(
                _event_aggregate(session, owner_id, entry.id) for entry in command.events
            )
            observation_results = tuple(
                _observation_aggregate(session, owner_id, entry.id)
                for entry in command.observations
            )
            if any(item is None for item in (*event_results, *observation_results)):
                raise RuntimeError("new daily save is missing a subtype row")
            invalidate_analytics(session, owner_id)
            return CreateDailyEntryResult(
                events=event_results,  # type: ignore[arg-type]
                observations=observation_results,  # type: ignore[arg-type]
                created=True,
            )
    except IntegrityError as exc:
        if not session.in_transaction():
            session.rollback()
        raise DailyConflict("one or more IDs are unavailable") from exc


def update_daily_item(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    expected_revision: int,
    record: DailyRecord,
    ai_use_allowed: bool | None = None,
    metadata: dict[str, Any] | None = None,
    *,
    write_source: Source | None = None,
    proposal_id: UUID | None = None,
    restore_archived: bool = False,
) -> DailyAggregate:
    try:
        with unit_of_work(session):
            owner = session.scalar(select(User).where(User.id == owner_id).with_for_update())
            if owner is None or owner.lifecycle != "active":
                raise DailyNotFound("owner does not exist")
            obj = session.scalar(
                select(HealthObject)
                .where(HealthObject.owner_id == owner_id, HealthObject.id == object_id)
                .with_for_update()
            )
            if obj is None:
                raise DailyNotFound
            expected_type = "event" if isinstance(record, EventSchemaV1) else "observation"
            if obj.object_type != expected_type:
                raise DailyNotFound
            if obj.status != "active" and not (restore_archived and obj.status == "archived"):
                raise DailyConflict("archived daily entries cannot be edited")
            if obj.revision != expected_revision:
                raise DailyConflict("daily entry has changed; reload before saving")
            aggregate = _daily_aggregate(session, owner_id, object_id)
            source = write_source or manual_source(session, owner_id)
            if restore_archived:
                obj.status = "active"
            obj.source_id = source.id
            obj.confirmation_status = (
                "unconfirmed" if source.source_kind == "device" else "user_confirmed"
            )
            if metadata is not None:
                obj.metadata_json = metadata
            if isinstance(record, EventSchemaV1):
                if not _is_event_aggregate(aggregate):
                    raise RuntimeError("Event aggregate is invalid")
                _, event, _, links = aggregate
                if links and (
                    record.domain != DailyDomain.SYMPTOMS
                    or record.payload.kind != EventKind.SYMPTOM
                ):
                    raise DailyValidationError(
                        "an Event with linked severity must remain a symptom episode"
                    )
                try:
                    validated = ProfileSchemaRegistry.validate(
                        "event", 1, record.payload.model_dump(mode="json")
                    )
                except ValidationError as exc:
                    raise DailyValidationError("Event payload is invalid") from exc
                if not isinstance(validated, EventPayloadSchemaV1):
                    raise TypeError("Event registry returned an incompatible payload type")
                event_values = _event_fields(record)
                event.event_kind = event_values["event_kind"]
                event.time_precision = event_values["time_precision"]
                event.occurred_at = event_values["occurred_at"]
                event.local_date = event_values["local_date"]
                event.timezone = event_values["timezone"]
                event.ended_at = event_values["ended_at"]
                event.payload = validated.root.model_dump(mode="json")
                obj.domain = record.domain.value
                obj.title = record.payload.label
                obj.notes = record.notes
                if ai_use_allowed is not None:
                    obj.ai_use_allowed = ai_use_allowed
                obj.revision += 1
                sequence = next_daily_sequence(session, owner_id)
                session.flush()
                _append_event_revision(
                    session,
                    owner_id,
                    obj,
                    event,
                    source,
                    links,
                    sequence,
                    "update",
                    proposal_id,
                )
            else:
                if not _is_observation_aggregate(aggregate):
                    raise RuntimeError("Observation aggregate is invalid")
                _, observation, _ = aggregate
                _validate_tracker_observation(session, owner_id, record, allow_archived=True)
                try:
                    validated = ProfileSchemaRegistry.validate(
                        "observation", 1, record.payload.model_dump(mode="json")
                    )
                except ValidationError as exc:
                    raise DailyValidationError("Observation payload is invalid") from exc
                if not isinstance(validated, ObservationPayloadV1):
                    raise TypeError("Observation registry returned an incompatible payload type")
                if not isinstance(observation, ObservationItem):
                    raise TypeError("Observation aggregate is invalid")
                linked_events = set(
                    session.scalars(
                        select(EventObservationLink.event_object_id).where(
                            EventObservationLink.owner_id == owner_id,
                            EventObservationLink.observation_object_id == object_id,
                        )
                    )
                )
                is_severity = record.payload.value.metric == MetricKey.SYMPTOM_SEVERITY
                if linked_events and not is_severity:
                    raise DailyValidationError(
                        "a linked symptom severity Observation cannot change metric"
                    )
                if is_severity and not linked_events:
                    raise DailyValidationError(
                        "symptom severity Observation requires a symptom Event"
                    )
                observation_values = _observation_fields(record)
                for name, value in observation_values.items():
                    setattr(observation, name, value)
                obj.domain = record.domain.value
                obj.title = (
                    "Custom tracker entry"
                    if isinstance(record.payload.value, CustomTrackerValueV1)
                    else record.payload.value.metric.value.replace("_", " ").title()
                )
                obj.notes = record.notes
                if ai_use_allowed is not None:
                    obj.ai_use_allowed = ai_use_allowed
                obj.revision += 1
                sequence = next_daily_sequence(session, owner_id)
                session.flush()
                _append_observation_revision(
                    session,
                    owner_id,
                    obj,
                    observation,
                    source,
                    sequence,
                    "update",
                    proposal_id,
                )
            session.flush()
            # An edit can move an existing row into a scope that never cited it.
            invalidate_analytics(session, owner_id)
            return _daily_aggregate(session, owner_id, object_id)
    except IntegrityError as exc:
        session.rollback()
        raise DailyConflict("daily entry conflicts with existing data") from exc


def archive_daily_item(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    expected_revision: int,
    *,
    expected_object_type: str | None = None,
    source_deletion: bool = False,
) -> DailyAggregate:
    with unit_of_work(session):
        owner = session.scalar(select(User).where(User.id == owner_id).with_for_update())
        if owner is None or owner.lifecycle != "active":
            raise DailyNotFound("owner does not exist")
        obj = session.scalar(
            select(HealthObject)
            .where(HealthObject.owner_id == owner_id, HealthObject.id == object_id)
            .with_for_update()
        )
        if (
            obj is None
            or obj.object_type not in {"event", "observation"}
            or (expected_object_type is not None and obj.object_type != expected_object_type)
        ):
            raise DailyNotFound
        if obj.status != "active":
            raise DailyConflict("daily entry is already archived")
        if obj.revision != expected_revision:
            raise DailyConflict("daily entry has changed; reload before saving")
        aggregate = _daily_aggregate(session, owner_id, object_id)
        source = aggregate[2]
        obj.status = "archived"
        obj.revision += 1
        if not source_deletion:
            import_identity = session.scalar(
                select(HealthKitImportIdentity)
                .where(
                    HealthKitImportIdentity.owner_id == owner_id,
                    HealthKitImportIdentity.object_id == object_id,
                )
                .with_for_update()
            )
            if import_identity is not None:
                import_identity.user_archived = True
        sequence = next_daily_sequence(session, owner_id)
        session.flush()
        if _is_event_aggregate(aggregate):
            _, event, _, links = aggregate
            _append_event_revision(
                session, owner_id, obj, event, source, links, sequence, "archive"
            )
        elif _is_observation_aggregate(aggregate):
            _, observation, _ = aggregate
            _append_observation_revision(
                session, owner_id, obj, observation, source, sequence, "archive"
            )
        else:
            raise RuntimeError("daily aggregate is invalid")
        session.flush()
        invalidate_analytics(session, owner_id, object_ids={object_id})
        return _daily_aggregate(session, owner_id, object_id)


def list_daily_history(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    after_revision: int,
    limit: int,
    *,
    exact_revision: int | None = None,
) -> list[HealthObjectRevision]:
    exists = session.scalar(
        select(HealthObject.id).where(
            HealthObject.owner_id == owner_id,
            HealthObject.id == object_id,
            HealthObject.object_type.in_(["event", "observation"]),
        )
    )
    if exists is None:
        raise DailyNotFound
    revision_condition = (
        HealthObjectRevision.revision == exact_revision
        if exact_revision is not None
        else HealthObjectRevision.revision > after_revision
    )
    return list(
        session.scalars(
            select(HealthObjectRevision)
            .where(
                HealthObjectRevision.owner_id == owner_id,
                HealthObjectRevision.object_id == object_id,
                revision_condition,
            )
            .order_by(HealthObjectRevision.revision)
            .limit(1 if exact_revision is not None else limit)
        )
    )
