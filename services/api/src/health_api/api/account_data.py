"""Authenticated owner export and explicit domain-erasure routes."""

from __future__ import annotations

from time import time
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from health_api.api.dependencies import get_current_owner, get_session, get_settings
from health_api.api.errors import APIError
from health_api.api.schemas import ErrorResponse, StrictModel
from health_api.application.account_data_service import (
    AccountDataConflict,
    AccountDataNotFound,
    AccountExportLimitExceeded,
    begin_owner_deletion,
    export_owner_snapshot,
    find_owner_deletion,
    load_owner_deletion,
    process_owner_deletion,
)
from health_api.config.settings import Settings
from health_api.persistence.models import OwnerDeletionJob
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

router = APIRouter(tags=["account-data"])

COMMON_ERRORS: dict[int, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Authentication is required or recent."},
    404: {"model": ErrorResponse, "description": "Owner data or deletion request was not found."},
    409: {
        "model": ErrorResponse,
        "description": "The owner lifecycle conflicts with this request.",
    },
    413: {"model": ErrorResponse, "description": "The bounded export limit was exceeded."},
    422: {"model": ErrorResponse, "description": "The request is invalid."},
    503: {"model": ErrorResponse, "description": "Health storage is unavailable."},
}


class OwnerDeletionRequest(StrictModel):
    request_id: UUID
    confirmation: Literal["DELETE MY HEALTH DATA"]


class OwnerDeletionResponse(StrictModel):
    request_id: UUID
    status: Literal["running", "failed", "completed"]
    requested_at: AwareDatetime
    completed_at: AwareDatetime | None
    error_code: Literal["object_storage_unavailable", "database_cleanup_failed"] | None


def _deletion_response(job: OwnerDeletionJob) -> OwnerDeletionResponse:
    return OwnerDeletionResponse(
        request_id=job.id,
        status=job.status,  # type: ignore[arg-type]
        requested_at=job.requested_at,
        completed_at=job.completed_at,
        error_code=job.error_code,  # type: ignore[arg-type]
    )


def _require_recent_authentication(request: Request, settings: Settings) -> None:
    if settings.auth_mode == "dev":
        return
    auth_time = getattr(request.state, "auth_time", None)
    now = int(time())
    if (
        isinstance(auth_time, bool)
        or not isinstance(auth_time, int)
        or auth_time > now + 60
        or now - auth_time > 300
    ):
        raise APIError(
            401,
            "recent_authentication_required",
            "Sign in again before requesting account data deletion.",
        )


@router.get(
    "/exports/current",
    operation_id="exportCurrentOwnerData",
    response_class=Response,
    responses={
        **COMMON_ERRORS,
        200: {"content": {"application/json": {"schema": {"type": "object"}}}},
    },
)
def export_current_owner_data(
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    try:
        serialized = export_owner_snapshot(session, owner_id)
    except AccountDataNotFound:
        raise APIError(404, "not_found", "Owner data was not found.") from None
    except AccountExportLimitExceeded:
        raise APIError(
            413,
            "export_too_large",
            "The owner snapshot exceeds the bounded download limit.",
        ) from None
    return Response(
        content=serialized,
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="personal-health-export-v1.json"',
        },
    )


@router.post(
    "/deletion-requests",
    operation_id="requestOwnerDataDeletion",
    response_model=OwnerDeletionResponse,
    status_code=202,
    responses=COMMON_ERRORS,
)
def request_owner_data_deletion(
    body: OwnerDeletionRequest,
    request: Request,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OwnerDeletionResponse:
    _require_recent_authentication(request, settings)
    try:
        begin_owner_deletion(session, owner_id, body.request_id)
        object_storage = request.app.state.object_storage
        job = process_owner_deletion(session, owner_id, body.request_id, object_storage)
    except AccountDataNotFound:
        raise APIError(404, "not_found", "Deletion request was not found.") from None
    except AccountDataConflict:
        raise APIError(409, "deletion_conflict", "Owner data is already being erased.") from None
    return _deletion_response(job)


@router.get(
    "/deletion-requests/current",
    operation_id="getCurrentOwnerDataDeletionRequest",
    response_model=OwnerDeletionResponse,
    responses=COMMON_ERRORS,
)
def get_current_owner_data_deletion_request(
    request: Request,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OwnerDeletionResponse:
    """Recover a pending or completed request after local request-ID loss."""
    _require_recent_authentication(request, settings)
    try:
        job = find_owner_deletion(session, owner_id)
    except AccountDataNotFound:
        raise APIError(404, "not_found", "Deletion request was not found.") from None
    return _deletion_response(job)


@router.get(
    "/deletion-requests/{request_id}",
    operation_id="getOwnerDataDeletionStatus",
    response_model=OwnerDeletionResponse,
    responses=COMMON_ERRORS,
)
def get_owner_data_deletion_status(
    request_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> OwnerDeletionResponse:
    try:
        job = load_owner_deletion(session, owner_id, request_id)
    except AccountDataNotFound:
        raise APIError(404, "not_found", "Deletion request was not found.") from None
    return _deletion_response(job)
