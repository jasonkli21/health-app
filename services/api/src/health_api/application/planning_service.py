"""Canonical persistence operations for owner-scoped planning resources."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from health_api.application.envelope_service import manual_source
from health_api.application.errors import (
    PlanningConflict,
    PlanningNotFound,
    PlanningValidationError,
)
from health_api.domain.daily import local_day_bounds
from health_api.domain.planning import (
    ContextPayloadV1,
    GoalPayloadV1,
    PlanPayloadV1,
    RegimenPayloadV1,
    ScheduleDefinitionV1,
    TrackerDefinitionV1,
)
from health_api.domain.scheduling import expand_schedule, schedule_matches_day
from health_api.persistence.models import (
    EventItem,
    HealthObject,
    HealthObjectRevision,
    PlanningLink,
    PlanningOccurrenceAction,
    PlanningOccurrenceOverride,
    PlanningResource,
    PlanningSchedule,
    PlanningScheduleIdentity,
    Source,
    TrackerSchemaVersion,
)

PlanningKind = Literal["goal", "regimen", "plan", "context", "tracker_definition"]
PlanningPayload = (
    GoalPayloadV1 | RegimenPayloadV1 | PlanPayloadV1 | ContextPayloadV1 | TrackerDefinitionV1
)
PlanningAggregate = tuple[HealthObject, PlanningResource, Source]

_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "goal": GoalPayloadV1,
    "regimen": RegimenPayloadV1,
    "plan": PlanPayloadV1,
    "context": ContextPayloadV1,
    "tracker_definition": TrackerDefinitionV1,
}
_ACTIVE_LIFECYCLES = {
    "goal": "active",
    "regimen": "active",
    "plan": "active",
    "context": "active",
    "tracker_definition": "active",
}


def _domain_for_payload(kind: str, payload: PlanningPayload) -> str:
    if kind in {"goal", "regimen"}:
        return payload.domain.value  # type: ignore[union-attr]
    if kind == "tracker_definition":
        return payload.domain.value  # type: ignore[union-attr]
    return "planning"


def _payload(kind: str, value: object) -> PlanningPayload:
    try:
        parsed = _PAYLOAD_MODELS[kind].model_validate(value)
    except (KeyError, ValidationError) as exc:
        raise PlanningValidationError("planning payload is invalid") from exc
    return cast(PlanningPayload, parsed)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _select_aggregate(
    session: Session, owner_id: UUID, object_id: UUID
) -> PlanningAggregate | None:
    row = session.execute(
        select(HealthObject, PlanningResource, Source)
        .join(
            PlanningResource,
            and_(
                PlanningResource.owner_id == HealthObject.owner_id,
                PlanningResource.object_id == HealthObject.id,
            ),
        )
        .join(
            Source,
            and_(Source.owner_id == HealthObject.owner_id, Source.id == HealthObject.source_id),
        )
        .where(HealthObject.owner_id == owner_id, HealthObject.id == object_id)
    ).one_or_none()
    return (row[0], row[1], row[2]) if row else None


def _link_specs(
    kind: str, payload: PlanningPayload
) -> list[tuple[UUID, str, UUID | None, str, int, str | None]]:
    if kind == "plan" and isinstance(payload, PlanPayloadV1):
        return [
            (
                item.id,
                f"plan_{item.kind.value}",
                item.reference_id,
                item.label,
                position,
                None,
            )
            for position, item in enumerate(payload.items)
        ]
    if kind == "context" and isinstance(payload, ContextPayloadV1):
        return [
            (
                UUID(int=position + 1),
                "context_relation",
                relation.object_id,
                "Context link",
                position,
                relation.relevance,
            )
            for position, relation in enumerate(payload.related)
        ]
    return []


def _validate_references(
    session: Session,
    owner_id: UUID,
    kind: str,
    payload: PlanningPayload,
) -> None:
    expected: dict[UUID, str] = {}
    for _, link_kind, target_id, _, _, _ in _link_specs(kind, payload):
        if target_id is None:
            continue
        if link_kind == "plan_goal":
            expected[target_id] = "goal"
        elif link_kind == "plan_regimen":
            expected[target_id] = "regimen"
        elif kind == "context":
            expected[target_id] = "context_target"
    if not expected:
        return
    rows = session.execute(
        select(HealthObject, PlanningResource)
        .outerjoin(
            PlanningResource,
            and_(
                PlanningResource.owner_id == HealthObject.owner_id,
                PlanningResource.object_id == HealthObject.id,
            ),
        )
        .where(HealthObject.owner_id == owner_id, HealthObject.id.in_(expected))
    ).all()
    found = {obj.id: (obj, resource) for obj, resource in rows}
    if set(found) != set(expected):
        raise PlanningNotFound
    for object_id, expected_kind in expected.items():
        obj, resource = found[object_id]
        if obj.status != "active":
            raise PlanningValidationError("archived resources cannot be linked")
        if expected_kind != "context_target" and (
            resource is None or resource.resource_kind != expected_kind
        ):
            raise PlanningValidationError("plan item reference has the wrong resource type")
        if expected_kind == "context_target" and (
            (resource is None and obj.object_type != "profile_item")
            or (resource is not None and resource.resource_kind not in {"goal", "regimen"})
        ):
            raise PlanningValidationError(
                "context relevance must reference Profile, goal, or regimen"
            )


def _sync_links(
    session: Session, owner_id: UUID, object_id: UUID, kind: str, payload: PlanningPayload
) -> None:
    specs = _link_specs(kind, payload)
    existing = list(
        session.scalars(
            select(PlanningLink)
            .where(
                PlanningLink.owner_id == owner_id,
                PlanningLink.parent_object_id == object_id,
            )
            .with_for_update()
        )
    )
    # Move positions out of the unique user-visible range before replacing an
    # order, avoiding transient collisions while retaining FK-referenced plan
    # item rows and their stable IDs.
    for position, existing_row in enumerate(existing):
        existing_row.position = 100 + position
    session.flush()
    wanted_ids = {spec[0] for spec in specs}
    existing_by_id = {row.link_id: row for row in existing}
    for existing_row in existing:
        if existing_row.link_id not in wanted_ids:
            session.delete(existing_row)
    for link_id, link_kind, target_id, label, position, relevance in specs:
        relation = payload.related[position] if isinstance(payload, ContextPayloadV1) else None
        row = existing_by_id.get(link_id)
        if row is None:
            row = PlanningLink(
                owner_id=owner_id,
                parent_object_id=object_id,
                link_id=link_id,
                link_kind=link_kind,
                target_object_id=target_id,
                label=label,
                position=position,
                priority=relation.priority if relation else 0,
                relevance=relevance,
            )
            session.add(row)
        else:
            row.link_kind = link_kind
            row.target_object_id = target_id
            row.label = label
            row.position = position
            row.priority = relation.priority if relation else 0
            row.relevance = relevance
    session.flush()


def _snapshot(aggregate: PlanningAggregate) -> dict[str, Any]:
    obj, resource, source = aggregate
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
        "resource_kind": resource.resource_kind,
        "lifecycle": resource.lifecycle,
        "current_schema_version": resource.current_schema_version,
        "payload": resource.payload,
    }


def _append_revision(
    session: Session, owner_id: UUID, aggregate: PlanningAggregate, reason: str
) -> None:
    obj, _, _ = aggregate
    session.add(
        HealthObjectRevision(
            owner_id=owner_id,
            object_id=obj.id,
            revision=obj.revision,
            actor_kind="user",
            actor_id=owner_id,
            reason=reason,
            snapshot=_snapshot(aggregate),
        )
    )


def create_planning_resource(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    kind: PlanningKind,
    input_payload: object,
    notes: str | None = None,
) -> tuple[PlanningAggregate, bool]:
    payload = _payload(kind, input_payload)
    fingerprint = hashlib.sha256(
        _canonical(
            {"kind": kind, "payload": payload.model_dump(mode="json"), "notes": notes}
        ).encode()
    ).hexdigest()
    try:
        with session.begin():
            existing = session.scalar(
                select(HealthObject).where(
                    HealthObject.owner_id == owner_id, HealthObject.id == object_id
                )
            )
            if existing:
                if existing.create_fingerprint != fingerprint:
                    raise PlanningConflict("this ID was already used for different content")
                aggregate = _select_aggregate(session, owner_id, object_id)
                if aggregate is None or aggregate[1].resource_kind != kind:
                    raise PlanningConflict("this ID belongs to another resource")
                return aggregate, False
            _validate_references(session, owner_id, kind, payload)
            source = manual_source(session, owner_id)
            life = _ACTIVE_LIFECYCLES[kind]
            obj = HealthObject(
                id=object_id,
                owner_id=owner_id,
                object_type=kind,
                domain=_domain_for_payload(kind, payload),
                status="active",
                title=getattr(payload, "label", getattr(payload, "name", "")),
                source_id=source.id,
                confirmation_status="user_confirmed",
                schema_version=1,
                revision=1,
                notes=notes,
                ai_use_allowed=False,
                cross_domain_use_allowed=False,
                create_fingerprint=fingerprint,
            )
            current_version = 1 if kind == "tracker_definition" else None
            resource = PlanningResource(
                owner_id=owner_id,
                object_id=object_id,
                resource_kind=kind,
                lifecycle=life,
                payload=payload.model_dump(mode="json"),
                current_schema_version=current_version,
            )
            session.add_all([obj, resource])
            session.flush()
            _sync_links(session, owner_id, object_id, kind, payload)
            if kind == "tracker_definition":
                session.add(
                    TrackerSchemaVersion(
                        owner_id=owner_id,
                        tracker_id=object_id,
                        version=1,
                        definition=payload.model_dump(mode="json"),
                    )
                )
            session.flush()
            aggregate = _select_aggregate(session, owner_id, object_id)
            if aggregate is None:
                raise RuntimeError("planning resource could not be reloaded")
            _append_revision(session, owner_id, aggregate, "create")
            session.flush()
            return aggregate, True
    except IntegrityError as exc:
        session.rollback()
        existing = session.scalar(
            select(HealthObject).where(
                HealthObject.owner_id == owner_id, HealthObject.id == object_id
            )
        )
        if existing and existing.create_fingerprint == fingerprint:
            aggregate = _select_aggregate(session, owner_id, object_id)
            if aggregate is not None:
                return aggregate, False
        if existing:
            raise PlanningConflict("this ID was already used for different content") from exc
        collision = session.scalar(select(HealthObject.id).where(HealthObject.id == object_id))
        if collision:
            raise PlanningConflict("this ID is unavailable") from exc
        raise


def get_planning_resource(
    session: Session, owner_id: UUID, object_id: UUID, kind: str | None = None
) -> PlanningAggregate:
    aggregate = _select_aggregate(session, owner_id, object_id)
    if aggregate is None or (kind is not None and aggregate[1].resource_kind != kind):
        raise PlanningNotFound
    return aggregate


def list_planning_resources(
    session: Session,
    owner_id: UUID,
    kind: PlanningKind,
    limit: int,
    lifecycle: str | None = None,
    after: tuple[datetime, UUID] | None = None,
) -> list[PlanningAggregate]:
    conditions = [
        HealthObject.owner_id == owner_id,
        HealthObject.status == "active",
        PlanningResource.resource_kind == kind,
    ]
    if lifecycle is not None:
        conditions.append(PlanningResource.lifecycle == lifecycle)
    if after is not None:
        conditions.append(
            or_(
                HealthObject.created_at < after[0],
                and_(HealthObject.created_at == after[0], HealthObject.id < after[1]),
            )
        )
    rows = session.execute(
        select(HealthObject, PlanningResource, Source)
        .join(
            PlanningResource,
            and_(
                PlanningResource.owner_id == HealthObject.owner_id,
                PlanningResource.object_id == HealthObject.id,
            ),
        )
        .join(
            Source,
            and_(Source.owner_id == HealthObject.owner_id, Source.id == HealthObject.source_id),
        )
        .where(*conditions)
        .order_by(HealthObject.created_at.desc(), HealthObject.id.desc())
        .limit(limit)
    ).all()
    return [(row[0], row[1], row[2]) for row in rows]


def update_planning_resource(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    kind: PlanningKind,
    expected_revision: int,
    input_payload: object,
) -> PlanningAggregate:
    payload = _payload(kind, input_payload)
    with session.begin():
        obj = session.scalar(
            select(HealthObject)
            .where(HealthObject.owner_id == owner_id, HealthObject.id == object_id)
            .with_for_update()
        )
        if obj is None or obj.object_type != kind:
            raise PlanningNotFound
        if obj.status != "active":
            raise PlanningConflict("archived planning resources cannot be edited")
        if obj.revision != expected_revision:
            raise PlanningConflict("planning resource has changed; reload before saving")
        resource = session.scalar(
            select(PlanningResource).where(
                PlanningResource.owner_id == owner_id,
                PlanningResource.object_id == object_id,
                PlanningResource.resource_kind == kind,
            )
        )
        if resource is None:
            raise PlanningNotFound
        _validate_references(session, owner_id, kind, payload)
        if kind == "plan" and isinstance(payload, PlanPayloadV1):
            candidate_ids = {item.id for item in payload.items}
            scheduled_ids = set(
                session.scalars(
                    select(PlanningScheduleIdentity.item_id).where(
                        PlanningScheduleIdentity.owner_id == owner_id,
                        PlanningScheduleIdentity.parent_object_id == object_id,
                        PlanningScheduleIdentity.item_id.is_not(None),
                    )
                )
            )
            if not scheduled_ids.issubset(candidate_ids):
                raise PlanningValidationError("scheduled plan items cannot be removed")
        resource.payload = payload.model_dump(mode="json")
        obj.title = getattr(payload, "label", getattr(payload, "name", ""))
        obj.domain = _domain_for_payload(kind, payload)
        if kind == "tracker_definition":
            if resource.current_schema_version is None:
                raise RuntimeError("tracker definition has no current schema version")
            resource.current_schema_version += 1
            session.add(
                TrackerSchemaVersion(
                    owner_id=owner_id,
                    tracker_id=object_id,
                    version=resource.current_schema_version,
                    definition=payload.model_dump(mode="json"),
                )
            )
        _sync_links(session, owner_id, object_id, kind, payload)
        obj.revision += 1
        obj.updated_at = datetime.now(UTC)
        session.flush()
        aggregate = _select_aggregate(session, owner_id, object_id)
        if aggregate is None:
            raise RuntimeError("updated planning resource could not be reloaded")
        _append_revision(session, owner_id, aggregate, "update")
        session.flush()
        return aggregate


def transition_planning_resource(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    kind: PlanningKind,
    expected_revision: int,
    lifecycle: str,
) -> PlanningAggregate:
    with session.begin():
        obj = session.scalar(
            select(HealthObject)
            .where(HealthObject.owner_id == owner_id, HealthObject.id == object_id)
            .with_for_update()
        )
        if obj is None or obj.object_type != kind:
            raise PlanningNotFound
        if obj.status != "active":
            raise PlanningConflict("archived planning resources cannot change lifecycle")
        if obj.revision != expected_revision:
            raise PlanningConflict("planning resource has changed; reload before saving")
        resource = session.scalar(
            select(PlanningResource).where(
                PlanningResource.owner_id == owner_id,
                PlanningResource.object_id == object_id,
                PlanningResource.resource_kind == kind,
            )
        )
        if resource is None:
            raise PlanningNotFound
        allowed = {
            "goal": {"active": {"paused", "completed"}, "paused": {"active", "completed"}},
            "regimen": {"active": {"paused", "completed"}, "paused": {"active", "completed"}},
            "plan": {"active": {"paused", "completed"}, "paused": {"active", "completed"}},
            "context": {"active": {"ended"}},
            "tracker_definition": {},
        }
        if lifecycle not in allowed[kind].get(resource.lifecycle, set()):
            raise PlanningConflict("lifecycle transition is not allowed")
        resource.lifecycle = lifecycle
        obj.revision += 1
        obj.updated_at = datetime.now(UTC)
        session.flush()
        aggregate = _select_aggregate(session, owner_id, object_id)
        if aggregate is None:
            raise RuntimeError("updated planning resource could not be reloaded")
        _append_revision(session, owner_id, aggregate, "update")
        session.flush()
        return aggregate


def archive_planning_resource(
    session: Session, owner_id: UUID, object_id: UUID, kind: PlanningKind, expected_revision: int
) -> PlanningAggregate:
    with session.begin():
        obj = session.scalar(
            select(HealthObject)
            .where(HealthObject.owner_id == owner_id, HealthObject.id == object_id)
            .with_for_update()
        )
        if obj is None or obj.object_type != kind:
            raise PlanningNotFound
        if obj.status == "archived":
            raise PlanningConflict("planning resource is already archived")
        if obj.revision != expected_revision:
            raise PlanningConflict("planning resource has changed; reload before saving")
        obj.status = "archived"
        obj.revision += 1
        obj.updated_at = datetime.now(UTC)
        session.flush()
        aggregate = _select_aggregate(session, owner_id, object_id)
        if aggregate is None:
            raise RuntimeError("archived planning resource could not be reloaded")
        _append_revision(session, owner_id, aggregate, "archive")
        session.flush()
        return aggregate


def list_planning_history(
    session: Session, owner_id: UUID, object_id: UUID, kind: str, after_revision: int, limit: int
) -> list[HealthObjectRevision]:
    get_planning_resource(session, owner_id, object_id, kind)
    return list(
        session.scalars(
            select(HealthObjectRevision)
            .where(
                HealthObjectRevision.owner_id == owner_id,
                HealthObjectRevision.object_id == object_id,
                HealthObjectRevision.revision > after_revision,
            )
            .order_by(HealthObjectRevision.revision.asc())
            .limit(limit)
        )
    )


def reorder_plan_items(
    session: Session,
    owner_id: UUID,
    plan_id: UUID,
    expected_revision: int,
    item_ids: list[UUID],
) -> PlanningAggregate:
    with session.begin():
        obj = session.scalar(
            select(HealthObject)
            .where(HealthObject.owner_id == owner_id, HealthObject.id == plan_id)
            .with_for_update()
        )
        if obj is None or obj.object_type != "plan":
            raise PlanningNotFound
        if obj.status != "active":
            raise PlanningConflict("archived plans cannot be reordered")
        if obj.revision != expected_revision:
            raise PlanningConflict("plan has changed; reload before saving")
        resource = session.scalar(
            select(PlanningResource).where(
                PlanningResource.owner_id == owner_id,
                PlanningResource.object_id == plan_id,
                PlanningResource.resource_kind == "plan",
            )
        )
        if resource is None:
            raise PlanningNotFound
        plan = _payload("plan", resource.payload)
        assert isinstance(plan, PlanPayloadV1)
        original_ids = [item.id for item in plan.items]
        if len(item_ids) != len(set(item_ids)) or set(item_ids) != set(original_ids):
            raise PlanningValidationError(
                "reorder must include each current plan item exactly once"
            )
        ordered = {item.id: item for item in plan.items}
        updated = PlanPayloadV1.model_validate(
            {**plan.model_dump(mode="json"), "items": [ordered[item_id] for item_id in item_ids]}
        )
        resource.payload = updated.model_dump(mode="json")
        obj.revision += 1
        obj.updated_at = datetime.now(UTC)
        session.flush()
        _sync_links(session, owner_id, plan_id, "plan", updated)
        aggregate = _select_aggregate(session, owner_id, plan_id)
        if aggregate is None:
            raise RuntimeError("reordered plan could not be reloaded")
        _append_revision(session, owner_id, aggregate, "update")
        session.flush()
        return aggregate


def _schedule_row_for_date(
    session: Session, owner_id: UUID, schedule_id: UUID, local_date: date
) -> PlanningSchedule | None:
    return session.scalar(
        select(PlanningSchedule)
        .where(
            PlanningSchedule.owner_id == owner_id,
            PlanningSchedule.schedule_id == schedule_id,
            PlanningSchedule.effective_from <= local_date,
        )
        .order_by(PlanningSchedule.effective_from.desc(), PlanningSchedule.revision.desc())
        .limit(1)
    )


def get_planning_schedule(
    session: Session,
    owner_id: UUID,
    parent_id: UUID,
    parent_kind: Literal["regimen", "plan"],
    item_id: UUID | None,
) -> dict[str, Any] | None:
    get_planning_resource(session, owner_id, parent_id, parent_kind)
    if parent_kind == "regimen" and item_id is not None:
        raise PlanningValidationError("regimen schedules belong to the regimen itself")
    if parent_kind == "plan":
        if item_id is None:
            raise PlanningValidationError("plan schedules must belong to a stable plan item")
        item = session.scalar(
            select(PlanningLink).where(
                PlanningLink.owner_id == owner_id,
                PlanningLink.parent_object_id == parent_id,
                PlanningLink.link_id == item_id,
            )
        )
        if item is None:
            raise PlanningNotFound
    identity = session.scalar(
        select(PlanningScheduleIdentity).where(
            PlanningScheduleIdentity.owner_id == owner_id,
            PlanningScheduleIdentity.parent_object_id == parent_id,
            PlanningScheduleIdentity.item_id == item_id,
        )
    )
    if identity is None:
        return None
    version = session.scalar(
        select(PlanningSchedule)
        .where(
            PlanningSchedule.owner_id == owner_id,
            PlanningSchedule.schedule_id == identity.schedule_id,
        )
        .order_by(PlanningSchedule.revision.desc())
        .limit(1)
    )
    if version is None:
        raise RuntimeError("schedule identity has no version")
    try:
        definition = ScheduleDefinitionV1.model_validate(version.definition)
    except ValidationError as exc:
        raise RuntimeError("stored schedule definition is invalid") from exc
    return {
        "schedule_id": identity.schedule_id,
        "schedule_revision": version.revision,
        "effective_from": version.effective_from,
        "schedule": definition,
    }


def _schedule_key(schedule_id: UUID, local_date: date, local_time: str) -> str:
    raw = _canonical({"s": str(schedule_id), "d": local_date.isoformat(), "t": local_time}).encode()
    import base64

    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _parse_schedule_key(key: str) -> tuple[UUID, date, str]:
    import base64

    try:
        if len(key) > 160:
            raise ValueError
        data = json.loads(base64.urlsafe_b64decode(key + "=" * (-len(key) % 4)))
        if set(data) != {"s", "d", "t"}:
            raise ValueError
        return UUID(data["s"]), date.fromisoformat(data["d"]), str(data["t"])
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlanningNotFound from exc


def set_planning_schedule(
    session: Session,
    owner_id: UUID,
    parent_id: UUID,
    parent_kind: Literal["regimen", "plan"],
    item_id: UUID | None,
    expected_revision: int | None,
    effective_from: date,
    definition: ScheduleDefinitionV1,
) -> dict[str, Any]:
    with session.begin():
        obj = session.scalar(
            select(HealthObject)
            .where(HealthObject.owner_id == owner_id, HealthObject.id == parent_id)
            .with_for_update()
        )
        if obj is None or obj.object_type != parent_kind:
            raise PlanningNotFound
        resource = session.scalar(
            select(PlanningResource).where(
                PlanningResource.owner_id == owner_id,
                PlanningResource.object_id == parent_id,
                PlanningResource.resource_kind == parent_kind,
            )
        )
        if obj.status != "active" or resource is None or resource.lifecycle != "active":
            raise PlanningConflict("only active plans and regimens can be scheduled")
        if parent_kind == "regimen" and item_id is not None:
            raise PlanningValidationError("regimen schedules belong to the regimen itself")
        if parent_kind == "plan":
            if item_id is None:
                raise PlanningValidationError("plan schedules must belong to a stable plan item")
            item = session.scalar(
                select(PlanningLink).where(
                    PlanningLink.owner_id == owner_id,
                    PlanningLink.parent_object_id == parent_id,
                    PlanningLink.link_id == item_id,
                )
            )
            if item is None:
                raise PlanningNotFound
        today = datetime.now(ZoneInfo(definition.timezone)).date()
        if effective_from < today:
            raise PlanningValidationError("schedules cannot be applied retroactively")
        identity = session.scalar(
            select(PlanningScheduleIdentity).where(
                PlanningScheduleIdentity.owner_id == owner_id,
                PlanningScheduleIdentity.parent_object_id == parent_id,
                PlanningScheduleIdentity.item_id == item_id,
            )
        )
        if identity is None:
            if expected_revision is not None:
                raise PlanningConflict("schedule no longer exists")
            identity = PlanningScheduleIdentity(
                owner_id=owner_id,
                schedule_id=uuid4(),
                parent_object_id=parent_id,
                item_id=item_id,
            )
            session.add(identity)
            session.flush()
            next_revision = 1
        else:
            rows = list(
                session.scalars(
                    select(PlanningSchedule)
                    .where(
                        PlanningSchedule.owner_id == owner_id,
                        PlanningSchedule.schedule_id == identity.schedule_id,
                    )
                    .order_by(PlanningSchedule.revision.desc())
                )
            )
            if not rows:
                raise RuntimeError("schedule identity has no version")
            current = rows[0]
            if expected_revision is None or current.revision != expected_revision:
                raise PlanningConflict("schedule has changed; reload before saving")
            if effective_from <= today or effective_from <= current.effective_from:
                raise PlanningValidationError("schedule edits must take effect on a future date")
            next_revision = current.revision + 1
        schedule = PlanningSchedule(
            owner_id=owner_id,
            schedule_id=identity.schedule_id,
            revision=next_revision,
            parent_object_id=parent_id,
            item_id=item_id,
            effective_from=effective_from,
            definition=definition.model_dump(mode="json"),
        )
        session.add(schedule)
        obj.revision += 1
        obj.updated_at = datetime.now(UTC)
        session.flush()
        aggregate = _select_aggregate(session, owner_id, parent_id)
        if aggregate is None:
            raise RuntimeError("scheduled resource could not be reloaded")
        session.add(
            HealthObjectRevision(
                owner_id=owner_id,
                object_id=parent_id,
                revision=obj.revision,
                actor_kind="user",
                actor_id=owner_id,
                reason="update",
                snapshot={
                    **_snapshot(aggregate),
                    "schedule": {
                        "id": str(identity.schedule_id),
                        "revision": next_revision,
                        "effective_from": effective_from.isoformat(),
                        "definition": definition.model_dump(mode="json"),
                    },
                },
            )
        )
        session.flush()
        return {
            "schedule_id": identity.schedule_id,
            "schedule_revision": next_revision,
            "effective_from": effective_from,
            "schedule": definition,
        }


def _schedule_parent_label(
    session: Session, owner_id: UUID, parent_id: UUID, item_id: UUID | None
) -> str:
    if item_id is not None:
        item = session.scalar(
            select(PlanningLink).where(
                PlanningLink.owner_id == owner_id,
                PlanningLink.parent_object_id == parent_id,
                PlanningLink.link_id == item_id,
            )
        )
        if item is None:
            raise PlanningNotFound
        return item.label
    obj = session.scalar(
        select(HealthObject).where(HealthObject.owner_id == owner_id, HealthObject.id == parent_id)
    )
    if obj is None:
        raise PlanningNotFound
    return obj.title


def list_planning_occurrences(
    session: Session,
    owner_id: UUID,
    parent_id: UUID,
    parent_kind: Literal["regimen", "plan"],
    start_date: date,
    end_date: date,
    timezone: str,
) -> list[dict[str, Any]]:
    if end_date < start_date or end_date == date.max or (end_date - start_date).days >= 31:
        raise PlanningValidationError("occurrence reads span at most 31 calendar days")
    try:
        window_start = local_day_bounds(start_date, timezone)[0]
        window_end = local_day_bounds(end_date, timezone)[1]
    except ValueError as exc:
        raise PlanningValidationError("occurrence timezone or date range is invalid") from exc
    parent = session.execute(
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
            HealthObject.id == parent_id,
            HealthObject.object_type == parent_kind,
        )
    ).one_or_none()
    if parent is None:
        raise PlanningNotFound
    if parent[0].status != "active" or parent[1].lifecycle != "active":
        return []
    identities = list(
        session.scalars(
            select(PlanningScheduleIdentity).where(
                PlanningScheduleIdentity.owner_id == owner_id,
                PlanningScheduleIdentity.parent_object_id == parent_id,
            )
        )
    )
    output: list[dict[str, Any]] = []
    for identity in identities:
        label = _schedule_parent_label(session, owner_id, parent_id, identity.item_id)
        candidate_dates: set[date] = set()
        current = max(date.min, start_date - timedelta(days=1))
        candidate_end = min(date.max - timedelta(days=1), end_date + timedelta(days=1))
        while current <= candidate_end:
            candidate_dates.add(current)
            current += timedelta(days=1)
        # A rescheduled slot keeps its original key and may be due on a date
        # far from that original local date. Add those original dates when the
        # new due instant falls inside this requested local-day window.
        moved_rows = list(
            session.scalars(
                select(PlanningOccurrenceOverride).where(
                    PlanningOccurrenceOverride.owner_id == owner_id,
                    PlanningOccurrenceOverride.schedule_id == identity.schedule_id,
                    PlanningOccurrenceOverride.state == "rescheduled",
                    PlanningOccurrenceOverride.rescheduled_at >= window_start,
                    PlanningOccurrenceOverride.rescheduled_at < window_end,
                )
            )
        )
        for moved in moved_rows:
            _, original_date, _ = _parse_schedule_key(moved.occurrence_key)
            candidate_dates.add(original_date)

        for original_date in sorted(candidate_dates):
            version = _schedule_row_for_date(session, owner_id, identity.schedule_id, original_date)
            if version is None:
                continue
            try:
                definition = ScheduleDefinitionV1.model_validate(version.definition)
            except ValidationError as exc:
                raise RuntimeError("stored schedule definition is invalid") from exc
            if not schedule_matches_day(definition, original_date):
                continue
            local_time_value = definition.local_time.isoformat()
            key = _schedule_key(identity.schedule_id, original_date, local_time_value)
            slot = expand_schedule(
                definition,
                original_date,
                original_date,
                schedule_id=str(identity.schedule_id),
                revision=version.revision,
                parent_id=str(parent_id),
                item_id=str(identity.item_id) if identity.item_id else None,
            )[0]
            override = session.get(PlanningOccurrenceOverride, (owner_id, key))
            state = override.state if override is not None else "unknown"
            due_at = (
                override.rescheduled_at
                if override and override.state == "rescheduled"
                else slot["due_at"]
            )
            if not isinstance(due_at, datetime):
                raise TypeError("expanded schedule did not include a due instant")
            if not (window_start <= due_at < window_end):
                continue
            output.append(
                {
                    "key": key,
                    "parent_id": parent_id,
                    "item_id": identity.item_id,
                    "label": label,
                    "schedule_id": identity.schedule_id,
                    "schedule_revision": version.revision,
                    "original_local_date": original_date,
                    "original_local_time": local_time_value,
                    "timezone": definition.timezone,
                    "due_at": due_at,
                    "dst_resolution": slot["dst_resolution"],
                    "state": state,
                    "override_revision": override.override_revision if override else None,
                    "linked_event_id": override.linked_event_id if override else None,
                }
            )
    output.sort(key=lambda item: (item["due_at"], str(item["parent_id"]), item["key"]))
    if len(output) > 500:
        raise PlanningValidationError("occurrence read exceeds 500 items")
    return output


def record_occurrence_action(
    session: Session,
    owner_id: UUID,
    key: str,
    expected_schedule_revision: int,
    expected_override_revision: int | None,
    state: Literal["completed", "skipped", "rescheduled"],
    rescheduled_at: datetime | None,
    linked_event_id: UUID | None,
) -> dict[str, Any]:
    schedule_id, local_date, local_time = _parse_schedule_key(key)
    with session.begin():
        identity = session.get(PlanningScheduleIdentity, (owner_id, schedule_id))
        if identity is None:
            raise PlanningNotFound
        parent = session.execute(
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
                HealthObject.id == identity.parent_object_id,
            )
            .with_for_update()
        ).one_or_none()
        if parent is None:
            raise PlanningNotFound
        if parent[0].status != "active" or parent[1].lifecycle != "active":
            raise PlanningConflict("inactive planning resources cannot change occurrences")
        version = _schedule_row_for_date(session, owner_id, schedule_id, local_date)
        if version is None:
            raise PlanningNotFound
        if version.revision != expected_schedule_revision:
            raise PlanningConflict("schedule changed; refresh occurrences before acting")
        definition = ScheduleDefinitionV1.model_validate(version.definition)
        if definition.local_time.isoformat() != local_time or not schedule_matches_day(
            definition, local_date
        ):
            raise PlanningNotFound
        occurrence = expand_schedule(
            definition,
            local_date,
            local_date,
            schedule_id=str(schedule_id),
            revision=version.revision,
            parent_id=str(identity.parent_object_id),
            item_id=str(identity.item_id) if identity.item_id else None,
        )[0]
        if state == "rescheduled":
            if rescheduled_at is None:
                raise PlanningValidationError("rescheduled occurrence requires a new due time")
            normalized_due = rescheduled_at.astimezone(UTC)
            original_due = occurrence["due_at"]
            if not isinstance(original_due, datetime):
                raise RuntimeError("expanded occurrence did not include a due instant")
            if (
                not original_due - timedelta(days=31)
                <= normalized_due
                <= original_due + timedelta(days=31)
            ):
                raise PlanningValidationError(
                    "rescheduled time must stay within 31 days of its original slot"
                )
        elif rescheduled_at is not None:
            raise PlanningValidationError("only rescheduled occurrences may include a new due time")
        else:
            normalized_due = None
        if linked_event_id is not None:
            linked = session.scalar(
                select(HealthObject.id)
                .join(
                    EventItem,
                    and_(
                        EventItem.owner_id == HealthObject.owner_id,
                        EventItem.object_id == HealthObject.id,
                    ),
                )
                .where(
                    HealthObject.owner_id == owner_id,
                    HealthObject.id == linked_event_id,
                    HealthObject.object_type == "event",
                    HealthObject.status == "active",
                )
            )
            if linked is None:
                raise PlanningNotFound
        current = session.get(PlanningOccurrenceOverride, (owner_id, key))
        if current is not None and (
            current.expected_schedule_revision == expected_schedule_revision
            and current.state == state
            and current.rescheduled_at == normalized_due
            and current.linked_event_id == linked_event_id
        ):
            return {
                "key": key,
                "state": current.state,
                "override_revision": current.override_revision,
                "schedule_revision": current.expected_schedule_revision,
                "rescheduled_at": current.rescheduled_at,
                "linked_event_id": current.linked_event_id,
                "updated_at": current.updated_at,
            }
        if current is None:
            if expected_override_revision is not None:
                raise PlanningConflict("occurrence was not previously changed")
            next_override_revision = 1
            current = PlanningOccurrenceOverride(
                owner_id=owner_id,
                occurrence_key=key,
                schedule_id=schedule_id,
                expected_schedule_revision=expected_schedule_revision,
                override_revision=next_override_revision,
                state=state,
                rescheduled_at=normalized_due,
                linked_event_id=linked_event_id,
            )
            session.add(current)
        else:
            if (
                expected_override_revision is None
                or current.override_revision != expected_override_revision
            ):
                raise PlanningConflict("occurrence action has changed; refresh before saving")
            next_override_revision = current.override_revision + 1
            current.expected_schedule_revision = expected_schedule_revision
            current.override_revision = next_override_revision
            current.state = state
            current.rescheduled_at = normalized_due
            current.linked_event_id = linked_event_id
            current.updated_at = datetime.now(UTC)
        session.flush()
        session.add(
            PlanningOccurrenceAction(
                owner_id=owner_id,
                occurrence_key=key,
                revision=next_override_revision,
                action=state,
                schedule_revision=expected_schedule_revision,
                actor_id=owner_id,
                rescheduled_at=normalized_due,
                linked_event_id=linked_event_id,
            )
        )
        session.flush()
        return {
            "key": key,
            "state": state,
            "override_revision": next_override_revision,
            "schedule_revision": expected_schedule_revision,
            "rescheduled_at": normalized_due,
            "linked_event_id": linked_event_id,
            "updated_at": current.updated_at,
        }


def load_today_planning(
    session: Session, owner_id: UUID, local_date: date, timezone: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    context_rows = session.execute(
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
            HealthObject.object_type == "context",
            HealthObject.status == "active",
            PlanningResource.lifecycle == "active",
        )
        .order_by(HealthObject.id.asc())
        .limit(501)
    ).all()
    if len(context_rows) > 500:
        raise PlanningValidationError("Today has too many active contexts")
    contexts: list[dict[str, Any]] = []
    for obj, resource in context_rows:
        payload = ContextPayloadV1.model_validate(resource.payload)
        if payload.start_at and local_date < payload.start_at:
            continue
        if payload.end_at and local_date >= payload.end_at:
            continue
        contexts.append(
            {
                "id": obj.id,
                "label": payload.label,
                "context_type": payload.context_type.value,
                "notes": payload.notes,
                "priority": payload.priority,
                "related": [item.model_dump(mode="json") for item in payload.related],
            }
        )
    contexts.sort(key=lambda item: (-item["priority"], str(item["id"])))

    schedule_parents = list(
        session.execute(
            select(HealthObject.id, HealthObject.object_type)
            .join(
                PlanningResource,
                and_(
                    PlanningResource.owner_id == HealthObject.owner_id,
                    PlanningResource.object_id == HealthObject.id,
                ),
            )
            .join(
                PlanningScheduleIdentity,
                and_(
                    PlanningScheduleIdentity.owner_id == HealthObject.owner_id,
                    PlanningScheduleIdentity.parent_object_id == HealthObject.id,
                ),
            )
            .where(
                HealthObject.owner_id == owner_id,
                HealthObject.status == "active",
                HealthObject.object_type.in_(["plan", "regimen"]),
                PlanningResource.lifecycle == "active",
            )
            .distinct()
            .limit(501)
        )
    )
    plan_items: list[dict[str, Any]] = []
    if len(schedule_parents) > 500:
        raise PlanningValidationError("Today has too many scheduled resources")
    for parent_id, parent_kind in schedule_parents:
        if parent_kind not in {"regimen", "plan"}:
            raise RuntimeError("scheduled resource has an invalid type")
        plan_items.extend(
            list_planning_occurrences(
                session,
                owner_id,
                parent_id,
                cast(Literal["regimen", "plan"], parent_kind),
                local_date,
                local_date,
                timezone,
            )
        )
        if len(plan_items) > 500:
            raise PlanningValidationError("Today has too many planned occurrences")
    return plan_items, contexts
