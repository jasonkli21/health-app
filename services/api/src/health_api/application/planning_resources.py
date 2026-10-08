"""Canonical persistence operations for owner-scoped planning resources."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from health_api.application.envelope_service import manual_source, unit_of_work
from health_api.application.errors import (
    PlanningConflict,
    PlanningNotFound,
    PlanningValidationError,
)
from health_api.application.planning_trackers import append_tracker_schema_version
from health_api.domain.planning import (
    ContextPayloadV1,
    GoalPayloadV1,
    PlanPayloadV1,
    RegimenPayloadV1,
    TrackerDefinitionV1,
)
from health_api.persistence.models import (
    HealthObject,
    HealthObjectRevision,
    PlanningLink,
    PlanningResource,
    PlanningScheduleIdentity,
    Source,
    User,
)
from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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


def _lock_planning_owner(session: Session, owner_id: UUID) -> None:
    if session.scalar(select(User.id).where(User.id == owner_id).with_for_update()) is None:
        raise PlanningNotFound


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
    allow_existing_inactive: set[tuple[UUID, str]] | None = None,
) -> None:
    expected: list[tuple[UUID, str]] = []
    for _, link_kind, target_id, _, _, _ in _link_specs(kind, payload):
        if target_id is None:
            continue
        if link_kind == "plan_goal":
            expected.append((target_id, "goal"))
        elif link_kind == "plan_regimen":
            expected.append((target_id, "regimen"))
        elif kind == "context":
            expected.append((target_id, "context_target"))
    if not expected:
        return
    target_ids = {target_id for target_id, _ in expected}
    rows = session.execute(
        select(HealthObject, PlanningResource)
        .outerjoin(
            PlanningResource,
            and_(
                PlanningResource.owner_id == HealthObject.owner_id,
                PlanningResource.object_id == HealthObject.id,
            ),
        )
        .where(HealthObject.owner_id == owner_id, HealthObject.id.in_(target_ids))
    ).all()
    found = {obj.id: (obj, resource) for obj, resource in rows}
    if set(found) != target_ids:
        raise PlanningNotFound
    for object_id, expected_kind in expected:
        obj, resource = found[object_id]
        existing_inactive_edge = allow_existing_inactive or set()
        if obj.status != "active" and (object_id, expected_kind) not in existing_inactive_edge:
            raise PlanningValidationError("archived resources cannot be linked")
        if expected_kind != "context_target" and (
            resource is None or resource.resource_kind != expected_kind
        ):
            raise PlanningValidationError("plan item reference has the wrong resource type")
        if (
            expected_kind != "context_target"
            and resource is not None
            and resource.lifecycle != "active"
            and (object_id, expected_kind) not in existing_inactive_edge
        ):
            raise PlanningValidationError("inactive resources cannot be linked")
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
            .order_by(PlanningLink.position, PlanningLink.link_id)
            .with_for_update()
        )
    )
    # Move positions out of the unique user-visible range before replacing an
    # order, avoiding transient collisions while retaining FK-referenced plan
    # item rows and their stable IDs.
    # Retired rows already occupy positions >= 100. The temporary range must
    # also be disjoint from those rows and the final retained-history range.
    temporary_base = (
        max((row.position for row in existing), default=0) + len(existing) + len(specs) + 101
    )
    for position, existing_row in enumerate(existing):
        existing_row.position = temporary_base + position
    session.flush()
    wanted_ids = {spec[0] for spec in specs}
    existing_by_id = {row.link_id: row for row in existing}
    for existing_index, existing_row in enumerate(existing):
        if existing_row.link_id not in wanted_ids:
            has_schedule = (
                session.scalar(
                    select(PlanningScheduleIdentity.schedule_id).where(
                        PlanningScheduleIdentity.owner_id == owner_id,
                        PlanningScheduleIdentity.parent_object_id == object_id,
                        PlanningScheduleIdentity.item_id == existing_row.link_id,
                    )
                )
                is not None
            )
            if has_schedule:
                existing_row.link_kind = "plan_retired"
                existing_row.position = 100 + len(specs) + existing_index
                existing_row.relevance = None
            else:
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
    session: Session,
    owner_id: UUID,
    aggregate: PlanningAggregate,
    reason: str,
    proposal_id: UUID | None = None,
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
            proposal_id=proposal_id,
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
    ai_use_allowed: bool = False,
    cross_domain_use_allowed: bool = False,
    *,
    write_source: Source | None = None,
    proposal_id: UUID | None = None,
) -> tuple[PlanningAggregate, bool]:
    payload = _payload(kind, input_payload)
    fingerprint_content: dict[str, Any] = {
        "kind": kind,
        "payload": payload.model_dump(mode="json"),
        "notes": notes,
    }
    if ai_use_allowed or cross_domain_use_allowed:
        fingerprint_content["permissions"] = {
            "ai_use_allowed": ai_use_allowed,
            "cross_domain_use_allowed": cross_domain_use_allowed,
        }
    fingerprint = hashlib.sha256(_canonical(fingerprint_content).encode()).hexdigest()
    try:
        with unit_of_work(session):
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
            source = write_source or manual_source(session, owner_id)
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
                ai_use_allowed=ai_use_allowed,
                cross_domain_use_allowed=cross_domain_use_allowed,
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
                append_tracker_schema_version(
                    session, owner_id, object_id, 1, payload.model_dump(mode="json")
                )
            session.flush()
            aggregate = _select_aggregate(session, owner_id, object_id)
            if aggregate is None:
                raise RuntimeError("planning resource could not be reloaded")
            _append_revision(session, owner_id, aggregate, "create", proposal_id)
            session.flush()
            return aggregate, True
    except IntegrityError as exc:
        if not session.in_transaction():
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
    archived: bool = False,
) -> list[PlanningAggregate]:
    conditions = [
        HealthObject.owner_id == owner_id,
        HealthObject.status == ("archived" if archived else "active"),
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
    ai_use_allowed: bool | None = None,
    cross_domain_use_allowed: bool | None = None,
    *,
    write_source: Source | None = None,
    proposal_id: UUID | None = None,
) -> PlanningAggregate:
    payload = _payload(kind, input_payload)
    with unit_of_work(session):
        _lock_planning_owner(session, owner_id)
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
        previous_payload = _payload(kind, resource.payload)
        previous_edges: set[tuple[UUID, str]] = set()
        if isinstance(previous_payload, PlanPayloadV1):
            previous_edges.update(
                (item.reference_id, item.kind.value)
                for item in previous_payload.items
                if item.reference_id is not None
            )
        elif isinstance(previous_payload, ContextPayloadV1):
            previous_edges.update(
                (item.object_id, "context_target") for item in previous_payload.related
            )
        _validate_references(session, owner_id, kind, payload, previous_edges)
        if kind == "plan" and isinstance(payload, PlanPayloadV1):
            candidate_ids = {item.id for item in payload.items}
            scheduled_ids = set(
                session.scalars(
                    select(PlanningScheduleIdentity.item_id).where(
                        PlanningScheduleIdentity.owner_id == owner_id,
                        PlanningScheduleIdentity.parent_object_id == object_id,
                        PlanningScheduleIdentity.item_id.is_not(None),
                        PlanningScheduleIdentity.retired_at.is_(None),
                    )
                )
            )
            removed_schedule_ids = scheduled_ids - candidate_ids
            if removed_schedule_ids:
                session.execute(
                    update(PlanningScheduleIdentity)
                    .where(
                        PlanningScheduleIdentity.owner_id == owner_id,
                        PlanningScheduleIdentity.parent_object_id == object_id,
                        PlanningScheduleIdentity.item_id.in_(removed_schedule_ids),
                    )
                    .values(retired_at=datetime.now(UTC))
                )
        resource.payload = payload.model_dump(mode="json")
        obj.title = getattr(payload, "label", getattr(payload, "name", ""))
        obj.domain = _domain_for_payload(kind, payload)
        if ai_use_allowed is not None:
            obj.ai_use_allowed = ai_use_allowed
        if cross_domain_use_allowed is not None:
            obj.cross_domain_use_allowed = cross_domain_use_allowed
        if write_source is not None:
            obj.source_id = write_source.id
            obj.confirmation_status = "user_confirmed"
        if kind == "tracker_definition":
            if resource.current_schema_version is None:
                raise RuntimeError("tracker definition has no current schema version")
            resource.current_schema_version += 1
            append_tracker_schema_version(
                session,
                owner_id,
                object_id,
                resource.current_schema_version,
                payload.model_dump(mode="json"),
            )
        _sync_links(session, owner_id, object_id, kind, payload)
        obj.revision += 1
        obj.updated_at = datetime.now(UTC)
        session.flush()
        aggregate = _select_aggregate(session, owner_id, object_id)
        if aggregate is None:
            raise RuntimeError("updated planning resource could not be reloaded")
        _append_revision(session, owner_id, aggregate, "update", proposal_id)
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
        _lock_planning_owner(session, owner_id)
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
        _lock_planning_owner(session, owner_id)
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
        _lock_planning_owner(session, owner_id)
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
