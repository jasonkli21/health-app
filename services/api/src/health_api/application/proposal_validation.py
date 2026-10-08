"""Non-mutating proposal command/evidence validation and review previews."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from health_api.application.daily_service import (
    CreateDailyEntry,
    CreateDailyEvent,
    CreateDailyLink,
    CreateDailyObservation,
    _validate_compound,
)
from health_api.application.errors import (
    ActionProposalValidationError,
    DailyNotFound,
    DailyValidationError,
    PlanningNotFound,
    PlanningValidationError,
)
from health_api.application.planning_service import (
    _link_specs,
    _payload,
    _validate_references,
    get_planning_resource,
)
from health_api.application.planning_trackers import validate_tracker_observation
from health_api.application.profile_service import (
    get_profile_item,
)
from health_api.application.proposal_support import _json_canonical, _parse_snapshot
from health_api.domain.planning import PlanPayloadV1
from health_api.domain.proposals import (
    EventCreateCommand,
    EvidenceReference,
    GoalCreateCommand,
    GoalUpdateCommand,
    PlanCreateCommand,
    PlanUpdateCommand,
    ProfileCreateCommand,
    ProfileUpdateCommand,
    StoredProposalContent,
    TrackerCreateCommand,
)
from health_api.domain.schemas import ProfileValidity
from health_api.persistence.models import (
    HealthObject,
    HealthObjectRevision,
)
from pydantic import ValidationError
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session


def _validate_evidence(session: Session, owner_id: UUID, evidence: list[EvidenceReference]) -> None:
    pairs = [(item.object_id, item.revision) for item in evidence]
    if len(set(pairs)) != len(pairs):
        raise ActionProposalValidationError("proposal evidence contains duplicates")
    for item in evidence:
        obj = session.scalar(
            select(HealthObject).where(
                HealthObject.owner_id == owner_id, HealthObject.id == item.object_id
            )
        )
        if obj is None or obj.revision != item.revision:
            raise ActionProposalValidationError("proposal evidence is unavailable or stale")


def _changed_reference_hints(
    session: Session, owner_id: UUID, content: StoredProposalContent
) -> list[dict[str, Any]]:
    expected: dict[UUID, tuple[int, str]] = {
        item.object_id: (item.revision, "evidence") for item in content.evidence_refs
    }
    for command in content.commands:
        if isinstance(command, (ProfileUpdateCommand, GoalUpdateCommand, PlanUpdateCommand)):
            expected[command.object_id] = (command.expected_revision, "target")
        if isinstance(command, (PlanCreateCommand, PlanUpdateCommand)):
            for item in command.reference_revisions:
                expected.setdefault(item.object_id, (item.revision, "plan_reference"))
    if not expected:
        return []
    objects = list(
        session.scalars(
            select(HealthObject).where(
                HealthObject.owner_id == owner_id, HealthObject.id.in_(expected)
            )
        )
    )
    by_id = {item.id: item for item in objects}
    current_pairs = [(item.id, item.revision) for item in objects]
    snapshots = (
        list(
            session.scalars(
                select(HealthObjectRevision).where(
                    HealthObjectRevision.owner_id == owner_id,
                    tuple_(HealthObjectRevision.object_id, HealthObjectRevision.revision).in_(
                        current_pairs
                    ),
                )
            )
        )
        if objects
        else []
    )
    latest = {(item.object_id, item.revision): item.snapshot for item in snapshots}
    hints: list[dict[str, Any]] = []
    for object_id, (expected_revision, reference_kind) in expected.items():
        obj = by_id.get(object_id)
        if obj is not None and obj.revision == expected_revision and obj.status == "active":
            continue
        hints.append(
            {
                "object_id": str(object_id),
                "reference_kind": reference_kind,
                "expected_revision": expected_revision,
                "current_revision": obj.revision if obj is not None else None,
                "current_status": obj.status if obj is not None else "unavailable",
                "current_title": obj.title if obj is not None else "Record unavailable",
                "current_snapshot": _bounded_review_snapshot(
                    latest.get((object_id, obj.revision), {}) if obj else {}
                ),
            }
        )
    return hints


def _bounded_review_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "object_type",
        "domain",
        "status",
        "title",
        "valid_from",
        "valid_to",
        "recorded_at",
        "revision",
        "notes",
        "profile",
        "payload",
        "resource_kind",
        "lifecycle",
    }
    candidate = {key: snapshot[key] for key in allowed if key in snapshot}
    encoded = _json_canonical(candidate)
    if len(encoded.encode("utf-8")) <= 4096:
        return candidate
    return {"truncated": True, "preview": encoded[:3500]}


def _validate_commands(
    session: Session,
    owner_id: UUID,
    snapshot: dict[str, Any],
    *,
    lock_references: bool = False,
) -> None:
    content = _parse_snapshot(snapshot)
    if lock_references:
        reference_ids = {item.object_id for item in content.evidence_refs}
        for command in content.commands:
            if isinstance(command, (ProfileUpdateCommand, GoalUpdateCommand, PlanUpdateCommand)):
                reference_ids.add(command.object_id)
            if isinstance(command, (PlanCreateCommand, PlanUpdateCommand)):
                reference_ids.update(
                    item.reference_id
                    for item in command.plan.items
                    if item.reference_id is not None
                )
        if reference_ids:
            # Hold target and evidence rows stable through apply. Sorting IDs
            # gives competing proposal transactions a consistent lock order.
            list(
                session.scalars(
                    select(HealthObject.id)
                    .where(
                        HealthObject.owner_id == owner_id,
                        HealthObject.id.in_(sorted(reference_ids)),
                    )
                    .order_by(HealthObject.id)
                    .with_for_update()
                )
            )
    _validate_evidence(session, owner_id, content.evidence_refs)
    updated_targets: set[UUID] = set()
    created_goal_positions = {
        command.id: index
        for index, command in enumerate(content.commands)
        if isinstance(command, GoalCreateCommand)
    }

    def validate_plan_references(
        plan: PlanPayloadV1,
        command_index: int,
        reference_revisions: list[EvidenceReference],
        allow_existing_inactive: set[tuple[UUID, str]] | None = None,
    ) -> None:
        proposal_goal_refs: set[UUID] = set()
        for item in plan.items:
            if item.reference_id not in created_goal_positions:
                continue
            goal_position = created_goal_positions[item.reference_id]
            if item.kind.value != "goal" or goal_position >= command_index:
                raise ActionProposalValidationError(
                    "a plan may reference a proposed Goal only after that Goal command"
                )
            proposal_goal_refs.add(item.reference_id)
        existing_items = [
            item for item in plan.items if item.reference_id not in proposal_goal_refs
        ]
        _validate_references(
            session,
            owner_id,
            "plan",
            plan.model_copy(update={"items": existing_items}),
            allow_existing_inactive,
        )
        stored_revisions = {item.object_id: item.revision for item in reference_revisions}
        for object_id in {
            item.reference_id for item in plan.items if item.reference_id is not None
        }:
            if object_id in proposal_goal_refs:
                continue
            obj = session.get(HealthObject, (owner_id, object_id))
            if obj is None or stored_revisions.get(object_id) != obj.revision:
                raise ActionProposalValidationError("Plan reference revision is stale")

    for command_index, command in enumerate(content.commands):
        if isinstance(command, ProfileCreateCommand):
            try:
                ProfileValidity(valid_from=command.valid_from, valid_to=command.valid_to)
            except ValidationError as exc:
                raise ActionProposalValidationError("Profile validity is invalid") from exc
            continue
        if isinstance(command, ProfileUpdateCommand):
            if command.object_id in updated_targets:
                raise ActionProposalValidationError("proposal updates one target more than once")
            updated_targets.add(command.object_id)
            profile_aggregate = get_profile_item(session, owner_id, command.object_id)
            obj = profile_aggregate[0]
            if obj.status != "active":
                raise ActionProposalValidationError("Profile target is archived")
            if obj.revision != command.expected_revision:
                raise ActionProposalValidationError("Profile target revision is stale")
            fields = command.model_fields_set
            try:
                ProfileValidity(
                    valid_from=(command.valid_from if "valid_from" in fields else obj.valid_from),
                    valid_to=(command.valid_to if "valid_to" in fields else obj.valid_to),
                )
            except ValidationError as exc:
                raise ActionProposalValidationError("Profile validity is invalid") from exc
            continue
        if isinstance(command, EventCreateCommand):
            observations = tuple(
                CreateDailyObservation(object_id, item)
                for object_id, item in zip(
                    command.observation_ids, command.linked_observations, strict=True
                )
            )
            daily = CreateDailyEntry(
                events=(CreateDailyEvent(command.event_id, command.event),),
                observations=observations,
                links=tuple(CreateDailyLink(command.event_id, item.id) for item in observations),
            )
            try:
                _validate_compound(daily)
                for observation in observations:
                    validate_tracker_observation(session, owner_id, observation.observation)
            except (DailyValidationError, DailyNotFound, ValidationError) as exc:
                raise ActionProposalValidationError(
                    "Event or linked Observation is invalid"
                ) from exc
            continue
        if isinstance(command, GoalCreateCommand):
            continue
        if isinstance(command, GoalUpdateCommand):
            if command.object_id in updated_targets:
                raise ActionProposalValidationError("proposal updates one target more than once")
            updated_targets.add(command.object_id)
            planning_aggregate = get_planning_resource(session, owner_id, command.object_id, "goal")
            if planning_aggregate[0].status != "active":
                raise ActionProposalValidationError("Goal target is archived")
            if planning_aggregate[0].revision != command.expected_revision:
                raise ActionProposalValidationError("Goal target revision is stale")
            continue
        if isinstance(command, PlanCreateCommand):
            try:
                validate_plan_references(command.plan, command_index, command.reference_revisions)
            except (PlanningNotFound, PlanningValidationError) as exc:
                raise ActionProposalValidationError("Plan references are invalid") from exc
            continue
        if isinstance(command, PlanUpdateCommand):
            if command.object_id in updated_targets:
                raise ActionProposalValidationError("proposal updates one target more than once")
            updated_targets.add(command.object_id)
            planning_aggregate = get_planning_resource(session, owner_id, command.object_id, "plan")
            if planning_aggregate[0].status != "active":
                raise ActionProposalValidationError("Plan target is archived")
            if planning_aggregate[0].revision != command.expected_revision:
                raise ActionProposalValidationError("Plan target revision is stale")
            previous = _payload("plan", planning_aggregate[1].payload)
            previous_edges = {
                (spec[2], "goal" if spec[1] == "plan_goal" else "regimen")
                for spec in _link_specs("plan", previous)
                if spec[2] is not None
            }
            try:
                validate_plan_references(
                    command.plan,
                    command_index,
                    command.reference_revisions,
                    previous_edges,
                )
            except (PlanningNotFound, PlanningValidationError) as exc:
                raise ActionProposalValidationError("Plan references are invalid") from exc
            continue
        if isinstance(command, TrackerCreateCommand):
            continue
        raise ActionProposalValidationError("unsupported action proposal command")
