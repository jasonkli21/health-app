"""Thin owner-authenticated action-proposal review and confirmation routes."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from health_api.api.dependencies import get_current_owner, get_session, get_settings
from health_api.api.errors import APIError
from health_api.api.schemas import ErrorResponse
from health_api.application.action_proposal_service import (
    action_proposal_history,
    action_proposal_state,
    apply_action_proposal,
    create_action_proposal,
    edit_action_proposal,
    get_action_proposal,
    list_action_proposals,
    reject_action_proposal,
)
from health_api.application.errors import ActionProposalExpired
from health_api.config.settings import Settings
from health_api.domain.proposals import (
    ProposalApplyRequest,
    ProposalApplyResponse,
    ProposalCreateRequest,
    ProposalEditRequest,
    ProposalHistoryEntry,
    ProposalHistoryResponse,
    ProposalListResponse,
    ProposalRejectRequest,
    ProposalState,
)

router = APIRouter(prefix="/action-proposals", tags=["action proposals"])
COMMON_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication is required or invalid."},
    404: {"model": ErrorResponse, "description": "Action proposal was not found."},
    409: {"model": ErrorResponse, "description": "Proposal or target revision conflict."},
    410: {"model": ErrorResponse, "description": "Action proposal has expired."},
    413: {"model": ErrorResponse, "description": "Request body exceeds the 65,536 byte limit."},
    422: {"model": ErrorResponse, "description": "Proposal commands are invalid or unsafe."},
    503: {"model": ErrorResponse, "description": "Proposal storage is unavailable."},
}


def _owner_binding(owner_id: UUID) -> str:
    return hashlib.sha256(owner_id.bytes).hexdigest()


def _encode_cursor(
    owner_id: UUID,
    state: str | None,
    after: tuple[datetime, UUID],
) -> str:
    payload = {
        "v": 1,
        "owner": _owner_binding(owner_id),
        "state": state,
        "created_at": after[0].astimezone(UTC).isoformat(),
        "id": str(after[1]),
    }
    return (
        base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )


def _decode_cursor(cursor: str, owner_id: UUID, state: str | None) -> tuple[datetime, UUID]:
    try:
        if len(cursor) > 2048:
            raise ValueError
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        payload = json.loads(raw)
        if set(payload) != {"v", "owner", "state", "created_at", "id"}:
            raise ValueError
        if (
            payload["v"] != 1
            or payload["owner"] != _owner_binding(owner_id)
            or payload["state"] != state
        ):
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError
        return created_at.astimezone(UTC), UUID(payload["id"])
    except (ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError) as exc:
        raise APIError(
            422, "invalid_cursor", "Proposal cursor is invalid for these filters."
        ) from exc


def _encode_history_cursor(owner_id: UUID, proposal_id: UUID, after: tuple[datetime, UUID]) -> str:
    payload = {
        "v": 1,
        "owner": _owner_binding(owner_id),
        "proposal": str(proposal_id),
        "recorded_at": after[0].astimezone(UTC).isoformat(),
        "event_id": str(after[1]),
    }
    return (
        base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )


def _decode_history_cursor(cursor: str, owner_id: UUID, proposal_id: UUID) -> tuple[datetime, UUID]:
    try:
        if len(cursor) > 2048:
            raise ValueError
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        payload = json.loads(raw)
        if set(payload) != {"v", "owner", "proposal", "recorded_at", "event_id"}:
            raise ValueError
        if (
            payload["v"] != 1
            or payload["owner"] != _owner_binding(owner_id)
            or payload["proposal"] != str(proposal_id)
        ):
            raise ValueError
        recorded_at = datetime.fromisoformat(payload["recorded_at"])
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            raise ValueError
        return recorded_at.astimezone(UTC), UUID(payload["event_id"])
    except (ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError) as exc:
        raise APIError(422, "invalid_cursor", "Proposal history cursor is invalid.") from exc


@router.get(
    "",
    response_model=ProposalListResponse,
    operation_id="listActionProposals",
    responses=COMMON_ERRORS,
)
def list_proposals(
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    state: Annotated[
        Literal["pending", "applied", "rejected", "expired", "superseded"] | None, Query()
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> ProposalListResponse:
    after = _decode_cursor(cursor, owner_id, state) if cursor else None
    rows = list_action_proposals(session, owner_id, limit + 1, state, after)
    more = len(rows) > limit
    page = rows[:limit]
    return ProposalListResponse(
        items=[action_proposal_state(session, owner_id, row) for row in page],
        next_cursor=(
            _encode_cursor(owner_id, state, (page[-1].created_at, page[-1].id))
            if more and page
            else None
        ),
    )


@router.post(
    "",
    response_model=ProposalState,
    status_code=201,
    operation_id="createActionProposal",
    responses={
        **COMMON_ERRORS,
        200: {"model": ProposalState, "description": "Idempotent proposal retry."},
    },
)
def create_proposal(
    body: ProposalCreateRequest,
    response: Response,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProposalState:
    state, created = create_action_proposal(
        session,
        owner_id,
        body.id,
        body,
        settings.action_proposal_ttl_hours,
        origin_kind="user",
        origin_metadata={"source": "owner-authored"},
    )
    response.status_code = 201 if created else 200
    return state


@router.get(
    "/{proposal_id}",
    response_model=ProposalState,
    operation_id="getActionProposal",
    responses=COMMON_ERRORS,
)
def get_proposal(
    proposal_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ProposalState:
    return get_action_proposal(session, owner_id, proposal_id)


@router.get(
    "/{proposal_id}/history",
    response_model=ProposalHistoryResponse,
    operation_id="listActionProposalHistory",
    responses=COMMON_ERRORS,
)
def get_proposal_history(
    proposal_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> ProposalHistoryResponse:
    after = _decode_history_cursor(cursor, owner_id, proposal_id) if cursor else None
    rows = action_proposal_history(session, owner_id, proposal_id, limit + 1, after)
    more = len(rows) > limit
    page = rows[:limit]
    return ProposalHistoryResponse(
        items=[
            ProposalHistoryEntry(
                event=cast(
                    Literal["created", "edited", "applied", "rejected", "expired"], row.event
                ),
                proposal_revision=row.proposal_revision,
                actor_id=row.actor_id,
                recorded_at=row.recorded_at,
                details=row.details,
            )
            for row in page
        ],
        next_cursor=(
            _encode_history_cursor(owner_id, proposal_id, (page[-1].recorded_at, page[-1].id))
            if more and page
            else None
        ),
    )


@router.patch(
    "/{proposal_id}",
    response_model=ProposalState,
    operation_id="editActionProposal",
    responses=COMMON_ERRORS,
)
def edit_proposal(
    proposal_id: UUID,
    body: ProposalEditRequest,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ProposalState:
    return edit_action_proposal(session, owner_id, proposal_id, body.expected_revision, body)


@router.post(
    "/{proposal_id}/apply",
    response_model=ProposalApplyResponse,
    operation_id="applyActionProposal",
    responses=COMMON_ERRORS,
)
def apply_proposal(
    proposal_id: UUID,
    body: ProposalApplyRequest,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ProposalApplyResponse:
    outcome = apply_action_proposal(
        session,
        owner_id,
        proposal_id,
        body.proposal_revision,
        body.content_hash,
        body.idempotency_key,
    )
    if outcome.error == "expired":
        raise ActionProposalExpired
    if outcome.error == "invalidated":
        raise APIError(
            409,
            "proposal_invalidated",
            "One or more referenced records changed. Refresh and review this proposal before confirming.",
        )
    return ProposalApplyResponse(proposal=outcome.state, replayed=outcome.replayed)


@router.post(
    "/{proposal_id}/reject",
    response_model=ProposalState,
    operation_id="rejectActionProposal",
    responses=COMMON_ERRORS,
)
def reject_proposal(
    proposal_id: UUID,
    body: ProposalRejectRequest,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ProposalState:
    return reject_action_proposal(
        session, owner_id, proposal_id, body.proposal_revision, body.reason
    )
