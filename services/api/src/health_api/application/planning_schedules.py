"""Schedule revisions, occurrence identity, and Today planning reads."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from health_api.application.errors import (
    PlanningConflict,
    PlanningNotFound,
    PlanningValidationError,
)
from health_api.application.planning_resources import (
    _canonical,
    _payload,
    _select_aggregate,
    _snapshot,
    get_planning_resource,
)
from health_api.domain.daily import local_day_bounds
from health_api.domain.planning import (
    ContextPayloadV1,
    ScheduleDefinitionV1,
)
from health_api.domain.scheduling import expand_schedule, schedule_matches_day
from health_api.persistence.models import (
    EventItem,
    HealthObject,
    HealthObjectRevision,
    ObservationItem,
    PlanningLink,
    PlanningOccurrenceAction,
    PlanningOccurrenceOverride,
    PlanningResource,
    PlanningSchedule,
    PlanningScheduleIdentity,
)
from pydantic import ValidationError
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session


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
        if (
            not key
            or len(key) > 160
            or any(
                ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
                for ch in key
            )
        ):
            raise ValueError
        raw = base64.b64decode(key + "=" * (-len(key) % 4), altchars=b"-_", validate=True)
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {"s", "d", "t"}:
            raise ValueError
        if not all(isinstance(data[name], str) for name in ("s", "d", "t")):
            raise ValueError
        schedule_id = UUID(data["s"])
        local_date = date.fromisoformat(data["d"])
        parsed_time = datetime.fromisoformat(f"2000-01-01T{data['t']}").time()
        if (
            str(schedule_id) != data["s"]
            or local_date <= date.min + timedelta(days=1)
            or local_date >= date.max - timedelta(days=1)
            or local_date.isoformat() != data["d"]
            or parsed_time.isoformat() != data["t"]
            or raw != _canonical({"s": data["s"], "d": data["d"], "t": data["t"]}).encode()
            or _schedule_key(schedule_id, local_date, data["t"]) != key
        ):
            raise ValueError
        return schedule_id, local_date, data["t"]
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
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
            if item is None or item.link_kind == "plan_retired":
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
            if identity.retired_at is not None:
                raise PlanningConflict("retired plan items cannot be scheduled")
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


def _payload_valid_on(payload: object, local_date: date) -> bool:
    start = getattr(payload, "start_date", None)
    end = getattr(payload, "end_date", None)
    return not (
        (start is not None and local_date < start) or (end is not None and local_date > end)
    )


def _occurrence_is_eligible(
    session: Session,
    owner_id: UUID,
    parent_obj: HealthObject,
    parent_resource: PlanningResource,
    identity: PlanningScheduleIdentity,
    local_date: date,
    timezone: str,
    links_by_id: dict[UUID, PlanningLink] | None = None,
    targets_by_id: dict[UUID, tuple[HealthObject, PlanningResource | None]] | None = None,
) -> bool:
    if parent_obj.status != "active" or parent_resource.lifecycle != "active":
        return False
    parent_payload = _payload(parent_resource.resource_kind, parent_resource.payload)
    if not _payload_valid_on(parent_payload, local_date):
        return False
    if parent_obj.valid_from is not None:
        try:
            if local_date < parent_obj.valid_from.astimezone(ZoneInfo(timezone)).date():
                return False
        except (ValueError, OverflowError):
            return False
    if parent_obj.valid_to is not None:
        try:
            if local_date >= parent_obj.valid_to.astimezone(ZoneInfo(timezone)).date():
                return False
        except (ValueError, OverflowError):
            return False
    if identity.item_id is None:
        return True
    link = (links_by_id or {}).get(identity.item_id)
    if link is None:
        link = session.scalar(
            select(PlanningLink).where(
                PlanningLink.owner_id == owner_id,
                PlanningLink.parent_object_id == identity.parent_object_id,
                PlanningLink.link_id == identity.item_id,
            )
        )
    if link is None or link.link_kind == "plan_retired":
        return False
    if link.target_object_id is None:
        return True
    target = (targets_by_id or {}).get(link.target_object_id)
    if target is None:
        target = session.execute(
            select(HealthObject, PlanningResource)
            .outerjoin(
                PlanningResource,
                and_(
                    PlanningResource.owner_id == HealthObject.owner_id,
                    PlanningResource.object_id == HealthObject.id,
                ),
            )
            .where(HealthObject.owner_id == owner_id, HealthObject.id == link.target_object_id)
        ).one_or_none()
        if target is None:
            return False
    target_obj, target_resource = target
    if (
        target_obj.status != "active"
        or target_resource is None
        or target_resource.lifecycle != "active"
    ):
        return False
    target_payload = _payload(target_resource.resource_kind, target_resource.payload)
    return _payload_valid_on(target_payload, local_date)


def _recorded_occurrence_details(
    override: PlanningOccurrenceOverride,
    versions: list[PlanningSchedule],
    schedule_id: UUID,
    parent_id: UUID,
    item_id: UUID | None,
) -> tuple[date, str, datetime, str, str] | None:
    try:
        _, original_date, original_time = _parse_schedule_key(override.occurrence_key)
    except PlanningNotFound:
        return None
    version = next(
        (item for item in versions if item.revision == override.expected_schedule_revision),
        None,
    )
    timezone_name = override.original_timezone
    dst_resolution = override.dst_resolution
    original_due_at = override.original_due_at
    if version is not None:
        definition = ScheduleDefinitionV1.model_validate(version.definition)
        timezone_name = timezone_name or definition.timezone
        if original_due_at is None or dst_resolution is None:
            original_slot = expand_schedule(
                definition,
                original_date,
                original_date,
                schedule_id=str(schedule_id),
                revision=version.revision,
                parent_id=str(parent_id),
                item_id=str(item_id) if item_id else None,
            )
            if original_slot:
                original_due_at = cast(datetime, original_slot[0]["due_at"])
                dst_resolution = dst_resolution or cast(str, original_slot[0]["dst_resolution"])
    due_at = override.rescheduled_at or original_due_at
    if due_at is None or timezone_name is None:
        return None
    return (
        original_date,
        original_time,
        due_at,
        timezone_name,
        dst_resolution or "exact",
    )


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
    if start_date <= date.min + timedelta(days=1) or end_date >= date.max - timedelta(days=1):
        raise PlanningValidationError("occurrence date range is outside the supported calendar")
    try:
        window_start = local_day_bounds(start_date, timezone)[0]
        window_end = local_day_bounds(end_date, timezone)[1]
    except (ValueError, OverflowError) as exc:
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
    parent_active = parent[0].status == "active" and parent[1].lifecycle == "active"
    identities = list(
        session.scalars(
            select(PlanningScheduleIdentity).where(
                PlanningScheduleIdentity.owner_id == owner_id,
                PlanningScheduleIdentity.parent_object_id == parent_id,
            )
        )
    )
    if not identities:
        return []
    schedule_ids = [identity.schedule_id for identity in identities]
    versions_by_schedule: dict[UUID, list[PlanningSchedule]] = {}
    for version in session.scalars(
        select(PlanningSchedule).where(
            PlanningSchedule.owner_id == owner_id,
            PlanningSchedule.schedule_id.in_(schedule_ids),
        )
    ):
        versions_by_schedule.setdefault(version.schedule_id, []).append(version)
    for versions in versions_by_schedule.values():
        versions.sort(key=lambda version: (version.effective_from, version.revision))
    overrides_by_schedule: dict[UUID, list[PlanningOccurrenceOverride]] = {}
    try:
        original_window_start = window_start - timedelta(days=2)
    except OverflowError:
        original_window_start = datetime.min.replace(tzinfo=UTC)
    try:
        original_window_end = window_end + timedelta(days=2)
    except OverflowError:
        original_window_end = datetime.max.replace(tzinfo=UTC)
    for override in session.scalars(
        select(PlanningOccurrenceOverride).where(
            PlanningOccurrenceOverride.owner_id == owner_id,
            PlanningOccurrenceOverride.schedule_id.in_(schedule_ids),
            or_(
                # Legacy overrides have no immutable due instant yet; decode
                # those against their saved schedule version until updated.
                PlanningOccurrenceOverride.original_due_at.is_(None),
                and_(
                    PlanningOccurrenceOverride.original_due_at >= original_window_start,
                    PlanningOccurrenceOverride.original_due_at < original_window_end,
                ),
                and_(
                    PlanningOccurrenceOverride.rescheduled_at >= window_start,
                    PlanningOccurrenceOverride.rescheduled_at < window_end,
                ),
            ),
        )
    ):
        overrides_by_schedule.setdefault(override.schedule_id, []).append(override)
    links_by_id = {
        row.link_id: row
        for row in session.scalars(
            select(PlanningLink).where(
                PlanningLink.owner_id == owner_id,
                PlanningLink.parent_object_id == parent_id,
                PlanningLink.link_id.in_(
                    [identity.item_id for identity in identities if identity.item_id is not None]
                ),
            )
        )
    }
    target_ids = {
        link.target_object_id for link in links_by_id.values() if link.target_object_id is not None
    }
    targets_by_id: dict[UUID, tuple[HealthObject, PlanningResource | None]] = {
        obj.id: (obj, resource)
        for obj, resource in session.execute(
            select(HealthObject, PlanningResource)
            .outerjoin(
                PlanningResource,
                and_(
                    PlanningResource.owner_id == HealthObject.owner_id,
                    PlanningResource.object_id == HealthObject.id,
                ),
            )
            .where(HealthObject.owner_id == owner_id, HealthObject.id.in_(target_ids))
        )
    }
    labels = {link_id: link.label for link_id, link in links_by_id.items()}
    output: list[dict[str, Any]] = []
    for identity in identities:
        label = labels.get(identity.item_id) if identity.item_id is not None else None
        if label is None:
            label = _schedule_parent_label(session, owner_id, parent_id, identity.item_id)
        versions = versions_by_schedule.get(identity.schedule_id, [])
        overrides = overrides_by_schedule.get(identity.schedule_id, [])
        recorded: set[str] = set()
        recorded_dates = {_parse_schedule_key(override.occurrence_key)[1] for override in overrides}
        for override in overrides:
            details = _recorded_occurrence_details(
                override, versions, identity.schedule_id, parent_id, identity.item_id
            )
            if details is None:
                continue
            original_date, original_time, due_at, timezone_name, dst_resolution = details
            if not (window_start <= due_at < window_end):
                continue
            output.append(
                {
                    "key": override.occurrence_key,
                    "parent_id": parent_id,
                    "item_id": identity.item_id,
                    "label": label,
                    "schedule_id": identity.schedule_id,
                    "schedule_revision": override.expected_schedule_revision,
                    "original_local_date": original_date,
                    "original_local_time": original_time,
                    "timezone": timezone_name,
                    "due_at": due_at,
                    "dst_resolution": dst_resolution,
                    "state": override.state,
                    "can_act": identity.retired_at is None
                    and _occurrence_is_eligible(
                        session,
                        owner_id,
                        parent[0],
                        parent[1],
                        identity,
                        original_date,
                        timezone_name,
                        links_by_id,
                        targets_by_id,
                    ),
                    "override_revision": override.override_revision,
                    "linked_event_id": override.linked_event_id,
                    "linked_observation_id": override.linked_observation_id,
                }
            )
            recorded.add(override.occurrence_key)
        if not parent_active or identity.retired_at is not None:
            continue
        candidate_dates: set[date] = set()
        current = start_date if start_date == date.min else start_date - timedelta(days=1)
        candidate_end = min(date.max - timedelta(days=1), end_date + timedelta(days=1))
        while current <= candidate_end:
            candidate_dates.add(current)
            current += timedelta(days=1)
        for original_date in sorted(candidate_dates):
            applicable = [
                version for version in versions if version.effective_from <= original_date
            ]
            selected_version = applicable[-1] if applicable else None
            if selected_version is None:
                continue
            try:
                definition = ScheduleDefinitionV1.model_validate(selected_version.definition)
            except ValidationError as exc:
                raise RuntimeError("stored schedule definition is invalid") from exc
            if not schedule_matches_day(definition, original_date):
                continue
            local_time_value = definition.local_time.isoformat()
            key = _schedule_key(identity.schedule_id, original_date, local_time_value)
            if key in recorded:
                continue
            if original_date in recorded_dates:
                continue
            if not _occurrence_is_eligible(
                session,
                owner_id,
                parent[0],
                parent[1],
                identity,
                original_date,
                definition.timezone,
                links_by_id,
                targets_by_id,
            ):
                continue
            slot = expand_schedule(
                definition,
                original_date,
                original_date,
                schedule_id=str(identity.schedule_id),
                revision=selected_version.revision,
                parent_id=str(parent_id),
                item_id=str(identity.item_id) if identity.item_id else None,
            )[0]
            expanded_due_at = slot["due_at"]
            if not isinstance(expanded_due_at, datetime):
                raise TypeError("expanded schedule did not include a due instant")
            if not (window_start <= expanded_due_at < window_end):
                continue
            output.append(
                {
                    "key": key,
                    "parent_id": parent_id,
                    "item_id": identity.item_id,
                    "label": label,
                    "schedule_id": identity.schedule_id,
                    "schedule_revision": selected_version.revision,
                    "original_local_date": original_date,
                    "original_local_time": local_time_value,
                    "timezone": definition.timezone,
                    "due_at": expanded_due_at,
                    "dst_resolution": slot["dst_resolution"],
                    "state": "unknown",
                    "can_act": True,
                    "override_revision": None,
                    "linked_event_id": None,
                    "linked_observation_id": None,
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
    linked_observation_id: UUID | None = None,
    replace_link: bool = True,
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
        current = session.get(PlanningOccurrenceOverride, (owner_id, key))
        version = (
            session.get(
                PlanningSchedule, (owner_id, schedule_id, current.expected_schedule_revision)
            )
            if current is not None
            else _schedule_row_for_date(session, owner_id, schedule_id, local_date)
        )
        if version is None:
            raise PlanningNotFound
        if version.revision != expected_schedule_revision:
            raise PlanningConflict("schedule changed; refresh occurrences before acting")
        if current is not None and not replace_link:
            linked_event_id = current.linked_event_id
            linked_observation_id = current.linked_observation_id
        definition = ScheduleDefinitionV1.model_validate(version.definition)
        if definition.local_time.isoformat() != local_time or not schedule_matches_day(
            definition, local_date
        ):
            raise PlanningNotFound
        if identity.retired_at is not None or not _occurrence_is_eligible(
            session, owner_id, parent[0], parent[1], identity, local_date, definition.timezone
        ):
            raise PlanningConflict("this occurrence is outside its resource's active validity")
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
            try:
                normalized_due = rescheduled_at.astimezone(UTC)
            except (ValueError, OverflowError) as exc:
                raise PlanningValidationError(
                    "rescheduled time is outside the supported range"
                ) from exc
            original_due = occurrence["due_at"]
            if not isinstance(original_due, datetime):
                raise RuntimeError("expanded occurrence did not include a due instant")
            try:
                lower_bound = original_due - timedelta(days=31)
            except OverflowError:
                lower_bound = datetime.min.replace(tzinfo=UTC)
            try:
                upper_bound = original_due + timedelta(days=31)
            except OverflowError:
                upper_bound = datetime.max.replace(tzinfo=UTC)
            if not lower_bound <= normalized_due <= upper_bound:
                raise PlanningValidationError(
                    "rescheduled time must stay within 31 days of its original slot"
                )
        elif rescheduled_at is not None:
            raise PlanningValidationError("only rescheduled occurrences may include a new due time")
        else:
            normalized_due = None
        if linked_event_id is not None and linked_observation_id is not None:
            raise PlanningValidationError("link at most one existing Event or Observation")
        if linked_event_id is not None and (current is None or replace_link):
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
        if linked_observation_id is not None and (current is None or replace_link):
            linked = session.scalar(
                select(HealthObject.id)
                .join(
                    ObservationItem,
                    and_(
                        ObservationItem.owner_id == HealthObject.owner_id,
                        ObservationItem.object_id == HealthObject.id,
                    ),
                )
                .where(
                    HealthObject.owner_id == owner_id,
                    HealthObject.id == linked_observation_id,
                    HealthObject.object_type == "observation",
                    HealthObject.status == "active",
                )
            )
            if linked is None:
                raise PlanningNotFound
        effective_moved_at = normalized_due
        if state != "rescheduled" and current is not None:
            effective_moved_at = current.rescheduled_at
        if current is not None and (
            current.expected_schedule_revision == expected_schedule_revision
            and current.state == state
            and current.rescheduled_at == effective_moved_at
            and current.linked_event_id == linked_event_id
            and current.linked_observation_id == linked_observation_id
        ):
            return {
                "key": key,
                "state": current.state,
                "override_revision": current.override_revision,
                "schedule_revision": current.expected_schedule_revision,
                "rescheduled_at": current.rescheduled_at,
                "linked_event_id": current.linked_event_id,
                "linked_observation_id": current.linked_observation_id,
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
                rescheduled_at=effective_moved_at,
                original_due_at=occurrence["due_at"],
                original_timezone=definition.timezone,
                dst_resolution=cast(str, occurrence["dst_resolution"]),
                linked_event_id=linked_event_id,
                linked_observation_id=linked_observation_id,
            )
            session.add(current)
        else:
            if (
                expected_override_revision is None
                or current.override_revision != expected_override_revision
            ):
                raise PlanningConflict("occurrence action has changed; refresh before saving")
            next_override_revision = current.override_revision + 1
            # Backfill legacy immutable provenance while retaining the schedule
            # version that created this recorded occurrence.
            current.original_due_at = current.original_due_at or cast(
                datetime, occurrence["due_at"]
            )
            current.original_timezone = current.original_timezone or definition.timezone
            current.dst_resolution = current.dst_resolution or cast(
                str, occurrence["dst_resolution"]
            )
            current.override_revision = next_override_revision
            current.state = state
            current.rescheduled_at = effective_moved_at
            current.linked_event_id = linked_event_id
            current.linked_observation_id = linked_observation_id
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
                rescheduled_at=effective_moved_at,
                linked_event_id=linked_event_id,
                linked_observation_id=linked_observation_id,
            )
        )
        session.flush()
        return {
            "key": key,
            "state": state,
            "override_revision": next_override_revision,
            "schedule_revision": expected_schedule_revision,
            "rescheduled_at": effective_moved_at,
            "linked_event_id": linked_event_id,
            "linked_observation_id": linked_observation_id,
            "updated_at": current.updated_at,
        }


def list_occurrence_history(
    session: Session, owner_id: UUID, key: str, after_revision: int, limit: int
) -> list[PlanningOccurrenceAction]:
    schedule_id, _, _ = _parse_schedule_key(key)
    identity = session.get(PlanningScheduleIdentity, (owner_id, schedule_id))
    if identity is None or session.get(PlanningOccurrenceOverride, (owner_id, key)) is None:
        raise PlanningNotFound
    return list(
        session.scalars(
            select(PlanningOccurrenceAction)
            .where(
                PlanningOccurrenceAction.owner_id == owner_id,
                PlanningOccurrenceAction.occurrence_key == key,
                PlanningOccurrenceAction.revision > after_revision,
            )
            .order_by(PlanningOccurrenceAction.revision.asc())
            .limit(limit)
        )
    )


def load_today_planning(
    session: Session, owner_id: UUID, local_date: date, timezone: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if local_date <= date.min + timedelta(days=1) or local_date >= date.max - timedelta(days=1):
        raise PlanningValidationError("Today date is outside the supported planning calendar")
    starts_on_or_before = PlanningResource.payload["start_at"].as_string() <= local_date.isoformat()
    ends_after = PlanningResource.payload["end_at"].as_string() > local_date.isoformat()
    window_start, window_end = local_day_bounds(local_date, timezone)
    # Discovery includes recorded history, even when the parent or item was
    # retired. The occurrence reader separately decides whether intent is active.
    recorded_in_window = exists(
        select(PlanningOccurrenceOverride.occurrence_key).where(
            PlanningOccurrenceOverride.owner_id == PlanningScheduleIdentity.owner_id,
            PlanningOccurrenceOverride.schedule_id == PlanningScheduleIdentity.schedule_id,
            or_(
                PlanningOccurrenceOverride.original_due_at.is_(None),
                and_(
                    func.coalesce(
                        PlanningOccurrenceOverride.rescheduled_at,
                        PlanningOccurrenceOverride.original_due_at,
                    )
                    >= window_start,
                    func.coalesce(
                        PlanningOccurrenceOverride.rescheduled_at,
                        PlanningOccurrenceOverride.original_due_at,
                    )
                    < window_end,
                ),
            ),
        )
    )
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
            or_(PlanningResource.payload["start_at"].as_string().is_(None), starts_on_or_before),
            or_(PlanningResource.payload["end_at"].as_string().is_(None), ends_after),
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
                HealthObject.object_type.in_(["plan", "regimen"]),
                or_(
                    and_(
                        HealthObject.status == "active",
                        PlanningResource.lifecycle == "active",
                        PlanningScheduleIdentity.retired_at.is_(None),
                        # Resource validity uses the schedule's local date, which
                        # can be adjacent to the requested display date.
                        or_(
                            PlanningResource.payload["start_date"].as_string().is_(None),
                            PlanningResource.payload["start_date"].as_string()
                            <= (local_date + timedelta(days=1)).isoformat(),
                        ),
                        or_(
                            PlanningResource.payload["end_date"].as_string().is_(None),
                            PlanningResource.payload["end_date"].as_string()
                            >= (local_date - timedelta(days=1)).isoformat(),
                        ),
                    ),
                    recorded_in_window,
                ),
            )
            .distinct()
        )
    )
    plan_items: list[dict[str, Any]] = []
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
    plan_items.sort(key=lambda item: (item["due_at"], str(item["parent_id"]), item["key"]))
    return plan_items, contexts
