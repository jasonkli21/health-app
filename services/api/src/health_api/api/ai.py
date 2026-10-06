"""Owner-scoped AI context, search and optional Assistant routes."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Any, cast, get_args
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from health_api.api.dependencies import get_current_owner, get_session
from health_api.api.errors import APIError
from health_api.api.schemas import (
    ErrorResponse,
)
from health_api.application.ai_context_service import build_ai_context, search_ai_resources
from health_api.application.today_service import owner_today_settings
from health_api.domain.ai import (
    AIContextPack,
    AIContextRequest,
    AIResourceType,
    AISearchResponse,
    AITaskKind,
    AssistantMessageRequest,
    AssistantMessageResponse,
    AssistantStatusResponse,
)
from health_api.integrations.personal_ai import (
    READ_CAPABILITIES,
    PersonalAIAdapter,
    PersonalAIAdapterError,
    PersonalAIUnavailable,
)

router = APIRouter(tags=["assistant"])

COMMON_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication is required or invalid."},
    413: {"model": ErrorResponse, "description": "Request body exceeds the 65,536 byte limit."},
    422: {"model": ErrorResponse, "description": "Request validation failed."},
    503: {"model": ErrorResponse, "description": "The optional Assistant is unavailable."},
}

_RESOURCE_TYPES = tuple(get_args(AIResourceType))
_RISK_RANK: dict[AITaskKind, int] = {
    "general_wellness": 0,
    "education": 1,
    "understand_health_data": 1,
    "consequential_medical": 2,
    "urgent_safety": 3,
}


def _owner_binding(owner_id: UUID) -> str:
    return hashlib.sha256(owner_id.bytes).hexdigest()


def _query_binding(query: str) -> str:
    return hashlib.sha256(query.strip().casefold().encode("utf-8")).hexdigest()


def _encode_cursor(
    owner_id: UUID,
    query: str,
    resource_types: tuple[AIResourceType, ...],
    after: tuple[datetime, UUID],
) -> str:
    payload = {
        "v": 1,
        "owner": _owner_binding(owner_id),
        "query": _query_binding(query),
        "types": sorted(resource_types),
        "recorded_at": after[0].astimezone(UTC).isoformat(),
        "id": str(after[1]),
    }
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def _decode_cursor(
    cursor: str,
    owner_id: UUID,
    query: str,
    resource_types: tuple[AIResourceType, ...],
) -> tuple[datetime, UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if set(payload) != {"v", "owner", "query", "types", "recorded_at", "id"}:
            raise ValueError
        if (
            payload["v"] != 1
            or payload["owner"] != _owner_binding(owner_id)
            or payload["query"] != _query_binding(query)
            or payload["types"] != sorted(resource_types)
        ):
            raise ValueError
        recorded_at = datetime.fromisoformat(payload["recorded_at"])
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            raise ValueError
        return recorded_at.astimezone(UTC), UUID(payload["id"])
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise APIError(
            422, "invalid_cursor", "Pagination cursor is invalid for these filters."
        ) from exc


def _parse_types(value: str | None) -> tuple[AIResourceType, ...]:
    if value is None:
        return cast(tuple[AIResourceType, ...], _RESOURCE_TYPES)
    raw_types = tuple(part.strip() for part in value.split(","))
    if (
        not raw_types
        or any(item not in _RESOURCE_TYPES for item in raw_types)
        or len(set(raw_types)) != len(raw_types)
    ):
        raise APIError(422, "invalid_resource_types", "Search resource types are invalid.")
    return cast(tuple[AIResourceType, ...], raw_types)


def _risk_floor(
    response: AssistantMessageResponse, requested: AITaskKind
) -> AssistantMessageResponse:
    if _RISK_RANK[response.risk_class] < _RISK_RANK[requested]:
        response.risk_class = requested
    return response


@router.get(
    "/assistant/status",
    response_model=AssistantStatusResponse,
    operation_id="getAssistantStatus",
    responses={401: COMMON_ERRORS[401]},
)
def assistant_status(
    request: Request,
    _owner_id: Annotated[UUID, Depends(get_current_owner)],
) -> AssistantStatusResponse:
    adapter = cast(PersonalAIAdapter, request.app.state.personal_ai_adapter)
    enabled = adapter.enabled
    return AssistantStatusResponse(
        enabled=enabled,
        adapter_status="ready" if enabled else "disabled",
        allowed_capabilities=list(READ_CAPABILITIES) if enabled else [],
        message=(
            "Assistant is ready for a read-only request."
            if enabled
            else "Assistant is unavailable until its service and privacy contract are configured."
        ),
    )


@router.post(
    "/ai/context",
    response_model=AIContextPack,
    operation_id="previewAIContext",
    responses=COMMON_ERRORS,
)
def preview_ai_context(
    body: AIContextRequest,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> AIContextPack:
    try:
        return build_ai_context(session, owner_id, body)
    except ValueError as exc:
        message = str(exc)
        code = (
            "context_budget_exceeded" if "safety constraint" in message else "invalid_context_scope"
        )
        raise APIError(422, code, message) from exc


@router.get(
    "/search",
    response_model=AISearchResponse,
    operation_id="searchAIEligibleHealthData",
    responses=COMMON_ERRORS,
)
def search_ai_eligible_health_data(
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str, Query(min_length=1, max_length=500)],
    types: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> AISearchResponse:
    resource_types = _parse_types(types)
    after = _decode_cursor(cursor, owner_id, q, resource_types) if cursor else None
    _, timezone = owner_today_settings(session, owner_id)
    try:
        items, next_after = search_ai_resources(
            session,
            owner_id,
            q,
            resource_types=resource_types,
            timezone=timezone,
            limit=limit,
            after=after,
        )
    except ValueError as exc:
        raise APIError(422, "invalid_search_scope", str(exc)) from exc
    next_cursor = (
        _encode_cursor(owner_id, q, resource_types, next_after) if next_after is not None else None
    )
    return AISearchResponse(items=items, next_cursor=next_cursor)


@router.post(
    "/assistant/messages",
    response_model=AssistantMessageResponse,
    operation_id="sendAssistantMessage",
    responses=COMMON_ERRORS,
)
async def send_assistant_message(
    body: AssistantMessageRequest,
    request: Request,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> AssistantMessageResponse:
    adapter = cast(PersonalAIAdapter, request.app.state.personal_ai_adapter)
    if not adapter.enabled:
        raise APIError(
            503,
            "assistant_unavailable",
            "Assistant is unavailable until its service and privacy contract are configured.",
        )
    try:
        context = build_ai_context(session, owner_id, body.scope, request_id=uuid4())
    except ValueError as exc:
        message = str(exc)
        code = (
            "context_budget_exceeded" if "safety constraint" in message else "invalid_context_scope"
        )
        raise APIError(422, code, message) from exc
    try:
        result = await adapter.send_message(body, context)
    except PersonalAIUnavailable:
        raise APIError(
            503, "assistant_unavailable", "Assistant is temporarily unavailable."
        ) from None
    except PersonalAIAdapterError:
        raise APIError(
            503, "assistant_unavailable", "Assistant is temporarily unavailable."
        ) from None
    permitted_refs = {(entry.object_id, entry.revision) for entry in context.entries}
    if any(
        (reference.object_id, reference.revision) not in permitted_refs
        for reference in result.evidence_refs
    ):
        raise APIError(
            503, "assistant_invalid_evidence", "Assistant returned unsupported evidence."
        )
    return _risk_floor(result, body.scope.task_kind)
