"""Transactional proposal confirmation, execution, receipts, and replay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from health_api.application.daily_service import (
    CreateDailyEntry,
    CreateDailyEvent,
    CreateDailyLink,
    CreateDailyObservation,
    create_daily_entry,
)
from health_api.application.envelope_service import proposal_source
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
    create_planning_resource,
    update_planning_resource,
)
from health_api.application.profile_service import (
    CreateProfile,
    create_profile_item,
    update_profile_item,
)
from health_api.application.proposal_support import (
    _append_event,
    _parse_snapshot,
    _state_from_row,
)
from health_api.application.proposal_validation import (
    _changed_reference_hints,
    _validate_commands,
)
from health_api.domain.proposals import (
    EventCreateCommand,
    GoalCreateCommand,
    GoalUpdateCommand,
    PlanCreateCommand,
    PlanUpdateCommand,
    ProfileCreateCommand,
    ProfileUpdateCommand,
    ProposalResult,
    ProposalState,
    StoredProposalContent,
    TrackerCreateCommand,
)
from health_api.domain.schemas import ProfileValidity
from health_api.persistence.models import (
    ActionCommandReceipt,
    ActionProposal,
    ActionProposalRevision,
    Source,
    User,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ApplyProposalOutcome:
    state: ProposalState
    replayed: bool
    error: Literal["expired", "invalidated"] | None = None


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
        # Match daily writes: hold the owner lock before proposal or target rows.
        owner = session.scalar(select(User).where(User.id == owner_id).with_for_update())
        if owner is None or owner.lifecycle != "active":
            raise ActionProposalNotFound
        prior_key = _find_receipt(session, owner_id, idempotency_key)
        if prior_key is not None:
            if (
                prior_key.proposal_id != proposal_id
                or prior_key.proposal_revision != proposal_revision
                or prior_key.content_hash != content_hash
            ):
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
            session.add(
                ActionCommandReceipt(
                    owner_id=owner_id,
                    proposal_id=proposal_id,
                    proposal_revision=proposal_revision,
                    idempotency_key=idempotency_key,
                    content_hash=content_hash,
                    result_json=original.result_json,
                )
            )
            session.flush()
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
            proposal.last_validation_summary = {
                "valid": False,
                "code": "reference_changed",
                "changed_references": _changed_reference_hints(session, owner_id, content),
            }
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
            proposal.last_validation_summary = {
                "valid": False,
                "code": "target_changed",
                "changed_references": _changed_reference_hints(session, owner_id, content),
            }
            proposal.updated_at = datetime.now(UTC)
            session.flush()
            return ApplyProposalOutcome(
                _state_from_row(session, proposal, owner_id), False, "invalidated"
            )

        return ApplyProposalOutcome(_state_from_row(session, proposal, owner_id), False)
