"""Owner-scoped proposal drafts and exactly-once confirmed command execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from health_api.application.daily_service import (
    CreateDailyEntry,
    CreateDailyEvent,
    CreateDailyLink,
    CreateDailyObservation,
    _validate_compound,
    _validate_tracker_observation,
    create_daily_entry,
)
from health_api.application.envelope_service import proposal_source, unit_of_work
from health_api.application.errors import (
    ActionProposalConflict,
    ActionProposalNotFound,
    ActionProposalValidationError,
    DailyConflict,
    DailyNotFound,
    DailyValidationError,
    PlanningConflict,
    PlanningNotFound,
    PlanningValidationError,
    ProfileConflict,
    ProfileNotFound,
    ProfileValidationError,
)
from health_api.application.planning_service import (
    _link_specs,
    _payload,
    _validate_references,
    create_planning_resource,
    get_planning_resource,
    update_planning_resource,
)
from health_api.application.profile_service import (
    CreateProfile,
    create_profile_item,
    get_profile_item,
    update_profile_item,
)
from health_api.domain.planning import PlanPayloadV1
from health_api.domain.proposals import (
    MAX_PROPOSAL_BYTES,
    MAX_PROPOSAL_LIFETIME_HOURS,
    EventCreateCommand,
    EventCreateDraft,
    EvidenceDetail,
    EvidenceReference,
    GoalCreateCommand,
    GoalCreateDraft,
    GoalUpdateCommand,
    PlanCreateCommand,
    PlanCreateDraft,
    PlanUpdateCommand,
    ProfileCreateCommand,
    ProfileCreateDraft,
    ProfileUpdateCommand,
    ProposalCommand,
    ProposalContent,
    ProposalResult,
    ProposalState,
    StoredProposalContent,
    TrackerCreateCommand,
    TrackerCreateDraft,
)
from health_api.domain.schemas import ProfileValidity
from health_api.persistence.models import (
    ActionCommandReceipt,
    ActionProposal,
    ActionProposalEvent,
    ActionProposalRevision,
    HealthObject,
    HealthObjectRevision,
    Source,
)

type ProposalStatus = Literal["pending", "applied", "rejected", "expired", "superseded"]


@dataclass(frozen=True)
class ApplyProposalOutcome:
    state: ProposalState
    replayed: bool
    error: Literal["expired", "invalidated"] | None = None


def _json_canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _draft_snapshot(content: ProposalContent, proposal_id: UUID) -> dict[str, Any]:
    commands: list[ProposalCommand] = []
    for index, command in enumerate(content.commands):
        # Keep the target UUID tied to the command slot across proposal edits.
        identity = uuid5(proposal_id, f"proposal-command:{index}:{command.action}")
        stored: ProposalCommand
        if isinstance(command, ProfileCreateDraft):
            stored = ProfileCreateCommand(
                **command.model_dump(mode="python", exclude_unset=True), id=identity
            )
        elif isinstance(command, EventCreateDraft):
            observation_ids = [
                uuid5(identity, f"observation:{observation_index}")
                for observation_index, _ in enumerate(command.linked_observations)
            ]
            stored = EventCreateCommand(
                **command.model_dump(mode="python", exclude_unset=True),
                event_id=identity,
                observation_ids=observation_ids,
            )
        elif isinstance(command, GoalCreateDraft):
            stored = GoalCreateCommand(
                **command.model_dump(mode="python", exclude_unset=True), id=identity
            )
        elif isinstance(command, PlanCreateDraft):
            stored = PlanCreateCommand(
                **command.model_dump(mode="python", exclude_unset=True), id=identity
            )
        elif isinstance(command, TrackerCreateDraft):
            stored = TrackerCreateCommand(
                **command.model_dump(mode="python", exclude_unset=True), id=identity
            )
        else:
            stored = command
        commands.append(stored)

    snapshot = {
        "rationale": content.rationale,
        "evidence_refs": [item.model_dump(mode="json") for item in content.evidence_refs],
        "commands": [item.model_dump(mode="json", exclude_unset=True) for item in commands],
    }
    encoded = _json_canonical(snapshot).encode("utf-8")
    if len(encoded) > MAX_PROPOSAL_BYTES:
        raise ActionProposalValidationError("proposal exceeds its bounded content size")
    return snapshot


def _content_hash(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(_json_canonical(snapshot).encode("utf-8")).hexdigest()


def _parse_snapshot(snapshot: dict[str, Any]) -> StoredProposalContent:
    try:
        return StoredProposalContent.model_validate(snapshot)
    except ValidationError as exc:
        raise RuntimeError("stored action proposal content is invalid") from exc


def _append_event(
    session: Session,
    proposal: ActionProposal,
    owner_id: UUID,
    event: str,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        ActionProposalEvent(
            owner_id=owner_id,
            proposal_id=proposal.id,
            proposal_revision=proposal.current_revision,
            event=event,
            actor_id=owner_id,
            details=details or {},
        )
    )


def _append_revision(
    session: Session,
    proposal: ActionProposal,
    owner_id: UUID,
    snapshot: dict[str, Any],
) -> None:
    session.add(
        ActionProposalRevision(
            owner_id=owner_id,
            proposal_id=proposal.id,
            revision=proposal.current_revision,
            schema_version=1,
            content_hash=proposal.content_hash,
            snapshot=snapshot,
            actor_id=owner_id,
        )
    )


def _state_from_row(
    session: Session, proposal: ActionProposal, owner_id: UUID, now: datetime | None = None
) -> ProposalState:
    revision = session.get(
        ActionProposalRevision, (owner_id, proposal.id, proposal.current_revision)
    )
    if revision is None:
        raise RuntimeError("action proposal has no current revision")
    content = _parse_snapshot(revision.snapshot)
    evidence_details: list[EvidenceDetail] = []
    for evidence in content.evidence_refs:
        evidence_revision = session.get(
            HealthObjectRevision, (owner_id, evidence.object_id, evidence.revision)
        )
        snapshot = evidence_revision.snapshot if evidence_revision is not None else {}
        evidence_details.append(
            EvidenceDetail(
                object_id=evidence.object_id,
                revision=evidence.revision,
                object_type=str(snapshot.get("object_type", "unavailable")),
                title=str(snapshot.get("title", "Source unavailable")),
            )
        )
    state: ProposalStatus = proposal.state  # type: ignore[assignment]
    current_time = now or datetime.now(UTC)
    if state == "pending" and proposal.expires_at <= current_time:
        state = "expired"
    results = [ProposalResult.model_validate(item) for item in (proposal.result_json or [])]
    return ProposalState(
        id=proposal.id,
        revision=proposal.current_revision,
        schema_version=1,
        content_hash=revision.content_hash,
        state=state,
        origin=proposal.origin_kind,  # type: ignore[arg-type]
        rationale=content.rationale,
        evidence_refs=evidence_details,
        commands=content.commands,
        created_at=proposal.created_at,
        expires_at=proposal.expires_at,
        updated_at=proposal.updated_at,
        last_validation_summary=proposal.last_validation_summary,
        confirmed_by=proposal.confirmed_by,
        confirmed_at=proposal.confirmed_at,
        applied_at=proposal.applied_at,
        rejected_by=proposal.rejected_by,
        rejected_at=proposal.rejected_at,
        reject_reason=proposal.reject_reason,
        results=results,
    )


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
                    _validate_tracker_observation(session, owner_id, observation.observation)
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
            if planning_aggregate[0].revision != command.expected_revision:
                raise ActionProposalValidationError("Goal target revision is stale")
            continue
        if isinstance(command, PlanCreateCommand):
            try:
                validate_plan_references(command.plan, command_index)
            except (PlanningNotFound, PlanningValidationError) as exc:
                raise ActionProposalValidationError("Plan references are invalid") from exc
            continue
        if isinstance(command, PlanUpdateCommand):
            if command.object_id in updated_targets:
                raise ActionProposalValidationError("proposal updates one target more than once")
            updated_targets.add(command.object_id)
            planning_aggregate = get_planning_resource(session, owner_id, command.object_id, "plan")
            if planning_aggregate[0].revision != command.expected_revision:
                raise ActionProposalValidationError("Plan target revision is stale")
            previous = _payload("plan", planning_aggregate[1].payload)
            previous_edges = {
                (spec[2], "goal" if spec[1] == "plan_goal" else "regimen")
                for spec in _link_specs("plan", previous)
                if spec[2] is not None
            }
            try:
                validate_plan_references(command.plan, command_index, previous_edges)
            except (PlanningNotFound, PlanningValidationError) as exc:
                raise ActionProposalValidationError("Plan references are invalid") from exc
            continue
        if isinstance(command, TrackerCreateCommand):
            continue
        raise ActionProposalValidationError("unsupported action proposal command")


def create_action_proposal(
    session: Session,
    owner_id: UUID,
    proposal_id: UUID,
    content: ProposalContent,
    expires_in_hours: int,
    *,
    origin_kind: Literal["user", "ai"] = "user",
    origin_metadata: dict[str, Any] | None = None,
) -> tuple[ProposalState, bool]:
    if not 1 <= expires_in_hours <= MAX_PROPOSAL_LIFETIME_HOURS:
        raise ActionProposalValidationError("proposal expiry is outside the supported server range")
    snapshot = _draft_snapshot(content, proposal_id)
    content_hash = _content_hash(snapshot)
    try:
        with unit_of_work(session):
            existing = session.scalar(
                select(ActionProposal)
                .where(ActionProposal.owner_id == owner_id, ActionProposal.id == proposal_id)
                .with_for_update()
            )
            if existing is not None:
                original_revision = session.get(ActionProposalRevision, (owner_id, proposal_id, 1))
                if original_revision is not None and original_revision.content_hash == content_hash:
                    return _state_from_row(session, existing, owner_id), False
                raise ActionProposalConflict("proposal ID was already used for different content")

            _validate_commands(session, owner_id, snapshot)
            now = datetime.now(UTC)
            proposal = ActionProposal(
                id=proposal_id,
                owner_id=owner_id,
                schema_version=1,
                state="pending",
                origin_kind=origin_kind,
                origin_metadata=origin_metadata or {"source": "owner-authored"},
                current_revision=1,
                content_hash=content_hash,
                created_at=now,
                updated_at=now,
                expires_at=now + timedelta(hours=expires_in_hours),
                last_validation_summary={"valid": True, "checked_at": now.isoformat()},
            )
            session.add(proposal)
            session.flush()
            _append_revision(session, proposal, owner_id, snapshot)
            _append_event(
                session,
                proposal,
                owner_id,
                "created",
                {
                    "expiry_hours": expires_in_hours,
                    "expiry_policy": "server-configured lifetime",
                },
            )
            session.flush()
            return _state_from_row(session, proposal, owner_id, now), True
    except IntegrityError as exc:
        session.rollback()
        existing = session.scalar(
            select(ActionProposal).where(
                ActionProposal.owner_id == owner_id, ActionProposal.id == proposal_id
            )
        )
        original_revision = (
            session.get(ActionProposalRevision, (owner_id, proposal_id, 1))
            if existing is not None
            else None
        )
        if (
            existing is not None
            and original_revision is not None
            and original_revision.content_hash == content_hash
        ):
            return _state_from_row(session, existing, owner_id), False
        raise ActionProposalConflict("proposal ID was already used") from exc


def get_action_proposal(session: Session, owner_id: UUID, proposal_id: UUID) -> ProposalState:
    proposal = session.scalar(
        select(ActionProposal).where(
            ActionProposal.owner_id == owner_id, ActionProposal.id == proposal_id
        )
    )
    if proposal is None:
        raise ActionProposalNotFound
    return _state_from_row(session, proposal, owner_id)


def action_proposal_state(
    session: Session, owner_id: UUID, proposal: ActionProposal
) -> ProposalState:
    return _state_from_row(session, proposal, owner_id)


def list_action_proposals(
    session: Session,
    owner_id: UUID,
    limit: int,
    state: ProposalStatus | None = None,
    after: tuple[datetime, UUID] | None = None,
) -> list[ActionProposal]:
    now = datetime.now(UTC)
    conditions: list[Any] = [ActionProposal.owner_id == owner_id]
    if state == "expired":
        conditions.append(
            or_(
                ActionProposal.state == "expired",
                and_(ActionProposal.state == "pending", ActionProposal.expires_at <= now),
            )
        )
    elif state is not None:
        conditions.append(ActionProposal.state == state)
        if state == "pending":
            conditions.append(ActionProposal.expires_at > now)
    if after is not None:
        conditions.append(
            or_(
                ActionProposal.created_at < after[0],
                and_(ActionProposal.created_at == after[0], ActionProposal.id < after[1]),
            )
        )
    return list(
        session.scalars(
            select(ActionProposal)
            .where(*conditions)
            .order_by(ActionProposal.created_at.desc(), ActionProposal.id.desc())
            .limit(limit)
        )
    )


def edit_action_proposal(
    session: Session,
    owner_id: UUID,
    proposal_id: UUID,
    expected_revision: int,
    content: ProposalContent,
) -> ProposalState:
    try:
        with session.begin():
            proposal = session.scalar(
                select(ActionProposal)
                .where(ActionProposal.owner_id == owner_id, ActionProposal.id == proposal_id)
                .with_for_update()
            )
            if proposal is None:
                raise ActionProposalNotFound
            if proposal.state != "pending":
                raise ActionProposalConflict("only a pending proposal can be edited")
            if proposal.expires_at <= datetime.now(UTC):
                proposal.state = "expired"
                proposal.updated_at = datetime.now(UTC)
                _append_event(session, proposal, owner_id, "expired")
                return _state_from_row(session, proposal, owner_id)
            if proposal.current_revision != expected_revision:
                raise ActionProposalConflict("proposal changed; review the current revision")
            next_revision = proposal.current_revision + 1
            snapshot = _draft_snapshot(content, proposal_id)
            _validate_commands(session, owner_id, snapshot)
            proposal.current_revision = next_revision
            proposal.content_hash = _content_hash(snapshot)
            proposal.updated_at = datetime.now(UTC)
            proposal.last_validation_summary = {
                "valid": True,
                "checked_at": proposal.updated_at.isoformat(),
            }
            session.flush()
            _append_revision(session, proposal, owner_id, snapshot)
            _append_event(
                session, proposal, owner_id, "edited", {"superseded_revision": expected_revision}
            )
            session.flush()
            return _state_from_row(session, proposal, owner_id)
    except IntegrityError as exc:
        session.rollback()
        raise ActionProposalConflict("proposal edit conflicted with another update") from exc


def reject_action_proposal(
    session: Session,
    owner_id: UUID,
    proposal_id: UUID,
    proposal_revision: int,
    reason: str | None,
) -> ProposalState:
    with session.begin():
        proposal = session.scalar(
            select(ActionProposal)
            .where(ActionProposal.owner_id == owner_id, ActionProposal.id == proposal_id)
            .with_for_update()
        )
        if proposal is None:
            raise ActionProposalNotFound
        if proposal.current_revision != proposal_revision:
            raise ActionProposalConflict("proposal changed; review the current revision")
        if proposal.state == "pending" and proposal.expires_at <= datetime.now(UTC):
            proposal.state = "expired"
            proposal.updated_at = datetime.now(UTC)
            _append_event(session, proposal, owner_id, "expired")
        elif proposal.state != "pending":
            raise ActionProposalConflict("proposal is no longer pending")
        else:
            proposal.state = "rejected"
            proposal.rejected_by = owner_id
            proposal.rejected_at = datetime.now(UTC)
            proposal.reject_reason = reason
            proposal.updated_at = proposal.rejected_at
            _append_event(session, proposal, owner_id, "rejected")
        session.flush()
        return _state_from_row(session, proposal, owner_id)


def _target_results(
    session: Session,
    owner_id: UUID,
    proposal_id: UUID,
    content: StoredProposalContent,
    source: Source,
) -> list[ProposalResult]:
    results: list[ProposalResult] = []
    for command in content.commands:
        if isinstance(command, ProfileCreateCommand):
            result = create_profile_item(
                session,
                owner_id,
                CreateProfile(
                    id=command.id,
                    profile=command.profile,
                    validity=ProfileValidity(
                        valid_from=command.valid_from, valid_to=command.valid_to
                    ),
                    notes=command.notes,
                    metadata=command.metadata.root,
                ),
                source=source,
                proposal_id=proposal_id,
            )
            if not result.created:
                raise ActionProposalConflict("proposed Profile target ID is already in use")
            obj = result.aggregate[0]
            results.append(
                ProposalResult(object_id=obj.id, object_type="profile_item", revision=obj.revision)
            )
        elif isinstance(command, ProfileUpdateCommand):
            fields = command.model_fields_set
            changes: dict[str, Any] = {"profile": command.profile.model_dump(mode="json")}
            for name in ("valid_from", "valid_to", "notes", "metadata"):
                if name in fields:
                    value = getattr(command, name)
                    changes[name] = (
                        value.root if name == "metadata" and value is not None else value
                    )
            aggregate = update_profile_item(
                session,
                owner_id,
                command.object_id,
                command.expected_revision,
                changes,
                source=source,
                proposal_id=proposal_id,
            )
            results.append(
                ProposalResult(
                    object_id=aggregate[0].id,
                    object_type="profile_item",
                    revision=aggregate[0].revision,
                )
            )
        elif isinstance(command, EventCreateCommand):
            daily = CreateDailyEntry(
                events=(CreateDailyEvent(command.event_id, command.event),),
                observations=tuple(
                    CreateDailyObservation(object_id, observation)
                    for object_id, observation in zip(
                        command.observation_ids, command.linked_observations, strict=True
                    )
                ),
                links=tuple(
                    CreateDailyLink(command.event_id, object_id)
                    for object_id in command.observation_ids
                ),
            )
            created = create_daily_entry(
                session,
                owner_id,
                daily,
                write_source=source,
                proposal_id=proposal_id,
            )
            if not created.created:
                raise ActionProposalConflict("proposed Event target ID is already in use")
            results.extend(
                ProposalResult(object_id=row[0].id, object_type="event", revision=row[0].revision)
                for row in created.events
            )
            results.extend(
                ProposalResult(
                    object_id=row[0].id, object_type="observation", revision=row[0].revision
                )
                for row in created.observations
            )
        elif isinstance(command, GoalCreateCommand):
            goal_aggregate, was_created = create_planning_resource(
                session,
                owner_id,
                command.id,
                "goal",
                command.goal,
                command.notes,
                write_source=source,
                proposal_id=proposal_id,
            )
            if not was_created:
                raise ActionProposalConflict("proposed Goal target ID is already in use")
            results.append(
                ProposalResult(
                    object_id=goal_aggregate[0].id,
                    object_type="goal",
                    revision=goal_aggregate[0].revision,
                )
            )
        elif isinstance(command, GoalUpdateCommand):
            goal_aggregate = update_planning_resource(
                session,
                owner_id,
                command.object_id,
                "goal",
                command.expected_revision,
                command.goal,
                write_source=source,
                proposal_id=proposal_id,
            )
            results.append(
                ProposalResult(
                    object_id=goal_aggregate[0].id,
                    object_type="goal",
                    revision=goal_aggregate[0].revision,
                )
            )
        elif isinstance(command, PlanCreateCommand):
            plan_aggregate, was_created = create_planning_resource(
                session,
                owner_id,
                command.id,
                "plan",
                command.plan,
                command.notes,
                write_source=source,
                proposal_id=proposal_id,
            )
            if not was_created:
                raise ActionProposalConflict("proposed Plan target ID is already in use")
            results.append(
                ProposalResult(
                    object_id=plan_aggregate[0].id,
                    object_type="plan",
                    revision=plan_aggregate[0].revision,
                )
            )
        elif isinstance(command, PlanUpdateCommand):
            plan_aggregate = update_planning_resource(
                session,
                owner_id,
                command.object_id,
                "plan",
                command.expected_revision,
                command.plan,
                write_source=source,
                proposal_id=proposal_id,
            )
            results.append(
                ProposalResult(
                    object_id=plan_aggregate[0].id,
                    object_type="plan",
                    revision=plan_aggregate[0].revision,
                )
            )
        elif isinstance(command, TrackerCreateCommand):
            tracker_aggregate, was_created = create_planning_resource(
                session,
                owner_id,
                command.id,
                "tracker_definition",
                command.definition,
                command.notes,
                write_source=source,
                proposal_id=proposal_id,
            )
            if not was_created:
                raise ActionProposalConflict("proposed tracker target ID is already in use")
            results.append(
                ProposalResult(
                    object_id=tracker_aggregate[0].id,
                    object_type="tracker_definition",
                    revision=tracker_aggregate[0].revision,
                )
            )
        else:
            raise ActionProposalValidationError("unsupported action proposal command")
    return results


def _find_receipt(
    session: Session, owner_id: UUID, idempotency_key: str
) -> ActionCommandReceipt | None:
    return session.scalar(
        select(ActionCommandReceipt).where(
            ActionCommandReceipt.owner_id == owner_id,
            ActionCommandReceipt.idempotency_key == idempotency_key,
        )
    )


def apply_action_proposal(
    session: Session,
    owner_id: UUID,
    proposal_id: UUID,
    proposal_revision: int,
    content_hash: str,
    idempotency_key: str,
) -> ApplyProposalOutcome:
    with session.begin():
        prior_key = _find_receipt(session, owner_id, idempotency_key)
        if prior_key is not None:
            if prior_key.proposal_id != proposal_id or prior_key.content_hash != content_hash:
                raise ActionProposalConflict(
                    "idempotency key was used for different proposal content"
                )
            proposal = session.scalar(
                select(ActionProposal).where(
                    ActionProposal.owner_id == owner_id, ActionProposal.id == proposal_id
                )
            )
            if proposal is None:
                raise ActionProposalNotFound
            return ApplyProposalOutcome(_state_from_row(session, proposal, owner_id), True)

        proposal = session.scalar(
            select(ActionProposal)
            .where(ActionProposal.owner_id == owner_id, ActionProposal.id == proposal_id)
            .with_for_update()
        )
        if proposal is None:
            raise ActionProposalNotFound

        if proposal.state == "applied":
            if proposal.applied_revision != proposal_revision:
                raise ActionProposalConflict("proposal confirmation revision is stale")
            original = session.scalar(
                select(ActionCommandReceipt).where(
                    ActionCommandReceipt.owner_id == owner_id,
                    ActionCommandReceipt.proposal_id == proposal_id,
                    ActionCommandReceipt.proposal_revision == proposal_revision,
                )
            )
            if original is None or original.content_hash != content_hash:
                raise ActionProposalConflict("applied proposal content does not match")
            return ApplyProposalOutcome(_state_from_row(session, proposal, owner_id), True)

        if proposal.state != "pending":
            raise ActionProposalConflict("proposal is no longer pending")
        if proposal.current_revision != proposal_revision:
            raise ActionProposalConflict("proposal confirmation revision is stale")
        revision = session.get(ActionProposalRevision, (owner_id, proposal_id, proposal_revision))
        if (
            revision is None
            or revision.content_hash != content_hash
            or proposal.content_hash != content_hash
        ):
            raise ActionProposalConflict("proposal content changed; review the current revision")

        now = datetime.now(UTC)
        if proposal.expires_at <= now:
            proposal.state = "expired"
            proposal.updated_at = now
            _append_event(session, proposal, owner_id, "expired")
            session.flush()
            return ApplyProposalOutcome(
                _state_from_row(session, proposal, owner_id, now), False, "expired"
            )

        content = _parse_snapshot(revision.snapshot)
        try:
            _validate_commands(session, owner_id, revision.snapshot, lock_references=True)
        except (ActionProposalValidationError, ProfileNotFound, PlanningNotFound, DailyNotFound):
            proposal.last_validation_summary = {"valid": False, "code": "reference_changed"}
            proposal.updated_at = now
            session.flush()
            return ApplyProposalOutcome(
                _state_from_row(session, proposal, owner_id, now), False, "invalidated"
            )

        try:
            with session.begin_nested():
                source = proposal_source(session, owner_id, proposal_id, proposal.origin_kind)
                results = _target_results(session, owner_id, proposal_id, content, source)
                result_payload = [item.model_dump(mode="json") for item in results]
                proposal.state = "applied"
                proposal.confirmed_by = owner_id
                proposal.confirmed_at = now
                proposal.applied_at = now
                proposal.applied_revision = proposal_revision
                proposal.updated_at = now
                proposal.result_json = result_payload
                proposal.last_validation_summary = {"valid": True, "applied_at": now.isoformat()}
                session.flush()
                _append_event(session, proposal, owner_id, "applied")
                session.add(
                    ActionCommandReceipt(
                        owner_id=owner_id,
                        proposal_id=proposal_id,
                        proposal_revision=proposal_revision,
                        idempotency_key=idempotency_key,
                        content_hash=content_hash,
                        result_json=result_payload,
                    )
                )
                session.flush()
        except (
            ProfileNotFound,
            ProfileConflict,
            ProfileValidationError,
            DailyNotFound,
            DailyConflict,
            DailyValidationError,
            PlanningNotFound,
            PlanningConflict,
            PlanningValidationError,
            IntegrityError,
        ) as exc:
            if isinstance(exc, IntegrityError):
                competing_receipt = _find_receipt(session, owner_id, idempotency_key)
                if competing_receipt is not None and (
                    competing_receipt.proposal_id != proposal_id
                    or competing_receipt.content_hash != content_hash
                ):
                    raise ActionProposalConflict(
                        "idempotency key was used for different proposal content"
                    ) from exc
            proposal.last_validation_summary = {"valid": False, "code": "target_changed"}
            proposal.updated_at = datetime.now(UTC)
            session.flush()
            return ApplyProposalOutcome(
                _state_from_row(session, proposal, owner_id), False, "invalidated"
            )

        return ApplyProposalOutcome(_state_from_row(session, proposal, owner_id), False)


def action_proposal_history(
    session: Session,
    owner_id: UUID,
    proposal_id: UUID,
    limit: int,
    after: tuple[datetime, UUID] | None = None,
) -> list[ActionProposalEvent]:
    exists = session.scalar(
        select(ActionProposal.id).where(
            ActionProposal.owner_id == owner_id, ActionProposal.id == proposal_id
        )
    )
    if exists is None:
        raise ActionProposalNotFound
    conditions: list[Any] = [
        ActionProposalEvent.owner_id == owner_id,
        ActionProposalEvent.proposal_id == proposal_id,
    ]
    if after is not None:
        conditions.append(
            or_(
                ActionProposalEvent.recorded_at > after[0],
                and_(
                    ActionProposalEvent.recorded_at == after[0],
                    ActionProposalEvent.id > after[1],
                ),
            )
        )
    return list(
        session.scalars(
            select(ActionProposalEvent)
            .where(*conditions)
            .order_by(ActionProposalEvent.recorded_at.asc(), ActionProposalEvent.id.asc())
            .limit(limit)
        )
    )
