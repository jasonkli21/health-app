"""Thin, typed Profile v1 HTTP routes."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from health_api.api.errors import APIError
from health_api.api.schemas import (
    ErrorResponse,
    ProfileCreateRequest,
    ProfileHistoryEntry,
    ProfileHistoryResponse,
    ProfileItemResponse,
    ProfileListResponse,
    ProfilePatchRequest,
)
from health_api.application.local_principal import ensure_local_principal
from health_api.application.profile_service import (
    CreateProfile,
    ProfileAggregate,
    archive_profile_item,
    create_profile_item,
    get_profile_item,
    list_profile_history,
    list_profile_items,
    update_profile_item,
)
from health_api.config.settings import Settings
from health_api.domain.schemas import ProfileCategory, ProfileMetadata, ProfileValidity
from health_api.persistence.models import HealthObjectRevision
from pydantic import AwareDatetime, ValidationError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/profile", tags=["profile"])
COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Local principal is unavailable."},
    413: {
        "model": ErrorResponse,
        "description": "Request body exceeds the 65,536 byte limit.",
    },
    422: {"model": ErrorResponse, "description": "Request validation failed."},
    503: {"model": ErrorResponse, "description": "Profile storage is unavailable."},
}
NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Profile item was not found."}
}
CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "Revision or ID conflict."}
}


def get_session(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_local_owner(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UUID:
    owner_id = ensure_local_principal(session, settings)
    if owner_id is None:
        raise APIError(401, "principal_unavailable", "Local principal is unavailable.")
    return owner_id


def item_response(aggregate: ProfileAggregate) -> ProfileItemResponse:
    health_object, profile_item, source = aggregate
    try:
        metadata = ProfileMetadata.model_validate(health_object.metadata_json)
    except ValidationError as exc:
        raise RuntimeError("stored Profile metadata is invalid") from exc
    return ProfileItemResponse.model_validate(
        {
            "id": health_object.id,
            "object_type": "profile_item",
            "domain": "profile",
            "status": health_object.status,
            "title": health_object.title,
            "valid_from": health_object.valid_from,
            "valid_to": health_object.valid_to,
            "recorded_at": health_object.recorded_at,
            "created_at": health_object.created_at,
            "updated_at": health_object.updated_at,
            "source": {"id": source.id, "kind": source.source_kind, "name": source.display_name},
            "confirmation_status": health_object.confirmation_status,
            "schema_version": 1,
            "revision": health_object.revision,
            "notes": health_object.notes,
            "metadata": metadata,
            "permissions": {
                "ai_use_allowed": health_object.ai_use_allowed,
                "cross_domain_use_allowed": health_object.cross_domain_use_allowed,
            },
            "profile": profile_item.payload,
        }
    )


def _owner_binding(owner_id: UUID) -> str:
    return hashlib.sha256(owner_id.bytes).hexdigest()


def _encode_cursor(
    owner_id: UUID,
    category: ProfileCategory | None,
    as_of: datetime,
    after: tuple[datetime, UUID],
) -> str:
    payload = {
        "v": 1,
        "owner": _owner_binding(owner_id),
        "category": category.value if category else None,
        "as_of": as_of.isoformat(),
        "created_at": after[0].isoformat(),
        "id": str(after[1]),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(
    value: str,
    owner_id: UUID,
    category: ProfileCategory | None,
    as_of: datetime,
) -> tuple[datetime, UUID]:
    try:
        if len(value) > 2048:
            raise ValueError
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(raw)
        if set(payload) != {"v", "owner", "category", "as_of", "created_at", "id"}:
            raise ValueError
        if (
            payload["v"] != 1
            or payload["owner"] != _owner_binding(owner_id)
            or payload["category"] != (category.value if category else None)
            or datetime.fromisoformat(payload["as_of"]).astimezone(UTC) != as_of
        ):
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError
        object_id = UUID(payload["id"])
        return created_at.astimezone(UTC), object_id
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise APIError(
            422, "invalid_cursor", "Pagination cursor is invalid for these filters."
        ) from exc


@router.get(
    "",
    response_model=ProfileListResponse,
    operation_id="listProfileItems",
    responses=COMMON_ERROR_RESPONSES,
)
def list_profiles(
    owner_id: Annotated[UUID, Depends(get_local_owner)],
    session: Annotated[Session, Depends(get_session)],
    as_of: Annotated[AwareDatetime | None, Query()] = None,
    category: Annotated[ProfileCategory | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> ProfileListResponse:
    effective_as_of = (as_of or datetime.now(UTC)).astimezone(UTC)
    after = _decode_cursor(cursor, owner_id, category, effective_as_of) if cursor else None
    results = list_profile_items(
        session,
        owner_id,
        effective_as_of,
        category.value if category else None,
        limit + 1,
        after,
    )
    has_more = len(results) > limit
    page = results[:limit]
    next_cursor = None
    if has_more and page:
        last_object = page[-1][0]
        next_cursor = _encode_cursor(
            owner_id,
            category,
            effective_as_of,
            (last_object.created_at, last_object.id),
        )
    return ProfileListResponse(
        items=[item_response(aggregate) for aggregate in page],
        as_of=effective_as_of,
        next_cursor=next_cursor,
    )


@router.post(
    "",
    response_model=ProfileItemResponse,
    status_code=201,
    operation_id="createProfileItem",
    responses={
        **COMMON_ERROR_RESPONSES,
        **CONFLICT_RESPONSE,
        200: {"model": ProfileItemResponse, "description": "Idempotent create retry."},
    },
)
def create_profile(
    body: ProfileCreateRequest,
    response: Response,
    owner_id: Annotated[UUID, Depends(get_local_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ProfileItemResponse:
    result = create_profile_item(
        session,
        owner_id,
        CreateProfile(
            id=body.id,
            profile=body.profile,
            validity=ProfileValidity(valid_from=body.valid_from, valid_to=body.valid_to),
            ai_use_allowed=body.ai_use_allowed,
            cross_domain_use_allowed=body.cross_domain_use_allowed,
            notes=body.notes,
            metadata=body.metadata.root,
        ),
    )
    response.status_code = 201 if result.created else 200
    return item_response(result.aggregate)


@router.get(
    "/{item_id}",
    response_model=ProfileItemResponse,
    operation_id="getProfileItem",
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)
def get_profile(
    item_id: UUID,
    owner_id: Annotated[UUID, Depends(get_local_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ProfileItemResponse:
    return item_response(get_profile_item(session, owner_id, item_id))


@router.get(
    "/{item_id}/history",
    response_model=ProfileHistoryResponse,
    operation_id="listProfileHistory",
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)
def get_profile_history(
    item_id: UUID,
    owner_id: Annotated[UUID, Depends(get_local_owner)],
    session: Annotated[Session, Depends(get_session)],
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ProfileHistoryResponse:
    revisions = list_profile_history(session, owner_id, item_id, after_revision, limit + 1)
    has_more = len(revisions) > limit
    page = revisions[:limit]
    entries = [_history_response(revision) for revision in page]
    next_revision = entries[-1].revision if has_more and entries else None
    return ProfileHistoryResponse(items=entries, next_after_revision=next_revision)


def _history_response(revision: HealthObjectRevision) -> ProfileHistoryEntry:
    snapshot: dict[str, Any] = revision.snapshot
    try:
        profile_response = ProfileItemResponse.model_validate(
            {
                **snapshot,
                "id": revision.object_id,
                "profile": snapshot["profile"],
                "metadata": snapshot["metadata"],
            }
        )
    except (ValidationError, KeyError) as exc:
        raise RuntimeError("stored Profile history is invalid") from exc
    return ProfileHistoryEntry.model_validate(
        {
            "revision": revision.revision,
            "recorded_at": revision.recorded_at,
            "actor_kind": revision.actor_kind,
            "reason": revision.reason,
            "snapshot": profile_response,
        }
    )


@router.patch(
    "/{item_id}",
    response_model=ProfileItemResponse,
    operation_id="updateProfileItem",
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE},
)
def patch_profile(
    item_id: UUID,
    body: ProfilePatchRequest,
    owner_id: Annotated[UUID, Depends(get_local_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ProfileItemResponse:
    changes = body.changes()
    if not changes:
        raise APIError(422, "empty_patch", "At least one Profile field must be changed.")
    aggregate = update_profile_item(session, owner_id, item_id, body.expected_revision, changes)
    return item_response(aggregate)


@router.delete(
    "/{item_id}",
    response_model=ProfileItemResponse,
    operation_id="archiveProfileItem",
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE},
)
def delete_profile(
    item_id: UUID,
    response: Response,
    owner_id: Annotated[UUID, Depends(get_local_owner)],
    session: Annotated[Session, Depends(get_session)],
    expected_revision: Annotated[int, Query(ge=1)],
) -> ProfileItemResponse:
    result = archive_profile_item(session, owner_id, item_id, expected_revision)
    response.status_code = 200
    return item_response(result)
