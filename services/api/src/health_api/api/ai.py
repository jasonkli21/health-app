"""Owner-scoped local AI context/search and disabled Assistant routes."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Any, cast, get_args
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
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
    AssistantMessageRequest,
    AssistantMessageResponse,
    AssistantStatusResponse,
)
from health_api.integrations.personal_ai import PersonalAIIntegrationStatus
from sqlalchemy.orm import Session

router = APIRouter(tags=["assistant"])

COMMON_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication is required or invalid."},
    413: {"model": ErrorResponse, "description": "Request body exceeds the 65,536 byte limit."},
    422: {"model": ErrorResponse, "description": "Request validation failed."},
    503: {"model": ErrorResponse, "description": "The optional Assistant is unavailable."},
}

_RESOURCE_TYPES = tuple(get_args(AIResourceType))


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
        payload = json.loads(base64.b64decode(cursor.encode(), altchars=b"-_", validate=True))
        if not isinstance(payload, dict) or set(payload) != {
            "v",
            "owner",
            "query",
            "types",
            "recorded_at",
            "id",
        }:
            raise ValueError
        if (
            type(payload["v"]) is not int
            or payload["v"] != 1
            or not isinstance(payload["owner"], str)
            or not isinstance(payload["query"], str)
            or not isinstance(payload["types"], list)
            or not isinstance(payload["recorded_at"], str)
            or not isinstance(payload["id"], str)
            or payload["owner"] != _owner_binding(owner_id)
            or payload["query"] != _query_binding(query)
            or payload["types"] != sorted(resource_types)
        ):
            raise ValueError
        recorded_at = datetime.fromisoformat(payload["recorded_at"])
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            raise ValueError
        return recorded_at.astimezone(UTC), UUID(payload["id"])
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OverflowError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
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
    """Return owner-authenticated status for the disabled external integration."""
    integration = cast(PersonalAIIntegrationStatus, request.app.state.personal_ai_status)
    return AssistantStatusResponse(
        enabled=integration.configured,
        adapter_status=integration.status,
        allowed_capabilities=[],
        message=integration.reason,
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
def send_assistant_message(
    body: AssistantMessageRequest,
    _owner_id: Annotated[UUID, Depends(get_current_owner)],
) -> AssistantMessageResponse:
    """Always return sanitized 503 until the shared contract is implemented and reviewed."""
    del body
    raise APIError(
        503,
        "assistant_unavailable",
        "Live Assistant messaging is unavailable until the Personal AI Application "
        "Integration Contract is implemented and reviewed.",
    )
