"""Canonical proposal snapshots, revision state, and review projections."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid5

from health_api.application.errors import (
    ActionProposalValidationError,
)
from health_api.domain.planning import PlanPayloadV1
from health_api.domain.proposals import (
    MAX_PROPOSAL_BYTES,
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
    ProposalChangeReview,
    ProposalCommand,
    ProposalContent,
    ProposalResult,
    ProposalState,
    StoredProposalContent,
    TrackerCreateCommand,
    TrackerCreateDraft,
)
from health_api.persistence.models import (
    ActionProposal,
    ActionProposalEvent,
    ActionProposalRevision,
    HealthObject,
    HealthObjectRevision,
    PlanningScheduleIdentity,
)
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

type ProposalStatus = Literal["pending", "applied", "rejected", "expired", "superseded"]


def _json_canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _draft_snapshot(
    content: ProposalContent, proposal_id: UUID, session: Session, owner_id: UUID
) -> dict[str, Any]:
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
            created_goal_ids = {
                uuid5(proposal_id, f"proposal-command:{goal_index}:goal.create")
                for goal_index, candidate in enumerate(content.commands)
                if isinstance(candidate, GoalCreateDraft)
            }
            references = _reference_revisions(session, owner_id, command.plan, created_goal_ids)
            stored = PlanCreateCommand(
                **command.model_dump(mode="python", exclude_unset=True),
                id=identity,
                reference_revisions=references,
            )
        elif isinstance(command, TrackerCreateDraft):
            stored = TrackerCreateCommand(
                **command.model_dump(mode="python", exclude_unset=True), id=identity
            )
        else:
            if isinstance(command, PlanUpdateCommand):
                created_goal_ids = {
                    uuid5(proposal_id, f"proposal-command:{goal_index}:goal.create")
                    for goal_index, candidate in enumerate(content.commands)
                    if isinstance(candidate, GoalCreateDraft)
                }
                stored = command.model_copy(
                    update={
                        "reference_revisions": _reference_revisions(
                            session, owner_id, command.plan, created_goal_ids
                        )
                    }
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


def _reference_revisions(
    session: Session, owner_id: UUID, plan: PlanPayloadV1, proposal_goal_ids: set[UUID]
) -> list[EvidenceReference]:
    reference_ids = {
        item.reference_id
        for item in plan.items
        if item.reference_id is not None and item.reference_id not in proposal_goal_ids
    }
    objects = (
        list(
            session.scalars(
                select(HealthObject)
                .where(HealthObject.owner_id == owner_id, HealthObject.id.in_(reference_ids))
                .order_by(HealthObject.id)
            )
        )
        if reference_ids
        else []
    )
    return [EvidenceReference(object_id=obj.id, revision=obj.revision) for obj in objects]


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
    changes = _proposal_changes(session, owner_id, content)
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
        changes=changes,
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


def _proposal_changes(
    session: Session, owner_id: UUID, content: StoredProposalContent
) -> list[ProposalChangeReview]:
    """Build a revision-bound review summary from the canonical target snapshot."""
    changes: list[ProposalChangeReview] = []
    for command in content.commands:
        if not isinstance(command, (ProfileUpdateCommand, GoalUpdateCommand, PlanUpdateCommand)):
            continue
        target = session.get(HealthObject, (owner_id, command.object_id))
        baseline = session.get(
            HealthObjectRevision, (owner_id, command.object_id, command.expected_revision)
        )
        before = baseline.snapshot if baseline is not None else {}
        after = command.model_dump(mode="json", exclude_unset=True)
        entry: dict[str, Any] = {
            "object_id": command.object_id,
            "object_type": target.object_type if target is not None else "unavailable",
            "title": before.get("title")
            or (target.title if target is not None else "Record unavailable"),
            "revision": command.expected_revision,
            "before": {},
            "after": {},
            "removed_plan_items": [],
            "schedules_to_retire": 0,
        }
        old_profile = before.get("profile", {})
        new_profile = after.get("profile", {})
        fields = command.model_fields_set
        if isinstance(command, ProfileUpdateCommand):
            field_map = {
                "profile": (old_profile, new_profile),
                "valid_from": (before.get("valid_from"), after.get("valid_from")),
                "valid_to": (before.get("valid_to"), after.get("valid_to")),
                "notes": (before.get("notes"), after.get("notes")),
                "metadata": (before.get("metadata"), after.get("metadata")),
            }
            changed = fields | {"profile"}
            for name in changed:
                old, new = field_map[name]
                entry["before"][name] = old
                entry["after"][name] = new
            preserved = [
                name
                for name in ("valid_from", "valid_to", "notes", "metadata")
                if name not in fields
            ]
            entry["preserved_fields"] = preserved
            entry["cleared_fields"] = [
                name for name in fields if name in field_map and getattr(command, name) is None
            ]
        elif isinstance(command, PlanUpdateCommand):
            old_items = before.get("payload", {}).get("items", [])
            new_items = after.get("plan", {}).get("items", [])
            new_ids = {item.get("id") for item in new_items}
            removed = [item for item in old_items if item.get("id") not in new_ids]
            entry["before"] = {"items": old_items}
            entry["after"] = {"items": new_items}
            entry["removed_plan_items"] = removed
            removed_ids = [item.get("id") for item in removed]
            if removed_ids:
                entry["schedules_to_retire"] = (
                    session.scalar(
                        select(func.count())
                        .select_from(PlanningScheduleIdentity)
                        .where(
                            PlanningScheduleIdentity.owner_id == owner_id,
                            PlanningScheduleIdentity.parent_object_id == command.object_id,
                            PlanningScheduleIdentity.item_id.in_(removed_ids),
                            PlanningScheduleIdentity.retired_at.is_(None),
                        )
                    )
                    or 0
                )
        else:
            entry["before"] = {"goal": before.get("payload")}
            entry["after"] = {"goal": after.get("goal")}
        changes.append(ProposalChangeReview.model_validate(entry))
    return changes
