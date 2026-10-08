"""Owner-scoped proposal lifecycle, revisions, and history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from health_api.application.envelope_service import unit_of_work
from health_api.application.errors import (
    ActionProposalConflict,
    ActionProposalNotFound,
    ActionProposalValidationError,
)
from health_api.application.proposal_support import (
    ProposalStatus,
    _append_event,
    _append_revision,
    _content_hash,
    _draft_snapshot,
    _parse_snapshot,
    _state_from_row,
)
from health_api.application.proposal_validation import _validate_commands
from health_api.domain.proposals import (
    MAX_PROPOSAL_LIFETIME_HOURS,
    ProposalContent,
    ProposalState,
    ProposalSummary,
)
from health_api.persistence.models import (
    ActionProposal,
    ActionProposalEvent,
    ActionProposalRevision,
)
from sqlalchemy import and_, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


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
    if origin_kind == "ai":
        raise ActionProposalValidationError(
            "AI-originated proposals are disabled until current-context safety policy is configured"
        )
    snapshot = _draft_snapshot(content, proposal_id, session, owner_id)
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
            # The event has a composite FK to this exact revision; SQLAlchemy
            # does not infer ordering between these independent mappings.
            session.flush()
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


def action_proposal_summaries(
    session: Session, owner_id: UUID, proposals: list[ActionProposal]
) -> list[ProposalSummary]:
    if not proposals:
        return []
    revision_rows = session.scalars(
        select(ActionProposalRevision).where(
            ActionProposalRevision.owner_id == owner_id,
            tuple_(ActionProposalRevision.proposal_id, ActionProposalRevision.revision).in_(
                [(item.id, item.current_revision) for item in proposals]
            ),
        )
    )
    by_key = {(item.proposal_id, item.revision): item for item in revision_rows}
    now = datetime.now(UTC)
    result: list[ProposalSummary] = []
    for proposal in proposals:
        revision = by_key.get((proposal.id, proposal.current_revision))
        if revision is None:
            raise RuntimeError("action proposal has no current revision")
        state: ProposalStatus = proposal.state  # type: ignore[assignment]
        if state == "pending" and proposal.expires_at <= now:
            state = "expired"
        content = _parse_snapshot(revision.snapshot)
        result.append(
            ProposalSummary(
                id=proposal.id,
                revision=proposal.current_revision,
                content_hash=revision.content_hash,
                state=state,
                origin=proposal.origin_kind,  # type: ignore[arg-type]
                rationale=content.rationale,
                created_at=proposal.created_at,
                expires_at=proposal.expires_at,
                updated_at=proposal.updated_at,
            )
        )
    return result


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
            snapshot = _draft_snapshot(content, proposal_id, session, owner_id)
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
            session.flush()
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
