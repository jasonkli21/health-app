"""Owner-scoped transport for optional normalized HealthKit imports."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from health_api.api.dependencies import get_current_owner, get_session
from health_api.api.errors import APIError
from health_api.api.schemas import (
    ErrorResponse,
)
from health_api.application.healthkit_import_service import (
    HealthKitImportConflict,
    HealthKitImportValidationError,
    get_healthkit_batch_receipt,
    get_healthkit_import_status,
    process_healthkit_import_batch,
    set_healthkit_source_preference,
)
from health_api.domain.healthkit_imports import (
    HealthKitImportBatchRequest,
    HealthKitImportBatchResult,
    HealthKitImportStatusResponse,
    HealthKitSourcePreferenceRequest,
    HealthKitSourcePreferenceResponse,
)

router = APIRouter(tags=["healthkit-imports"])

COMMON_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication is required or invalid."},
    413: {"model": ErrorResponse, "description": "Request body exceeds the route size limit."},
    422: {"model": ErrorResponse, "description": "The normalized import batch is invalid."},
    503: {"model": ErrorResponse, "description": "Health storage is unavailable."},
}


@router.post(
    "/imports/healthkit/batches",
    status_code=201,
    response_model=HealthKitImportBatchResult,
    operation_id="importHealthKitBatch",
    responses={
        **COMMON_ERRORS,
        200: {"model": HealthKitImportBatchResult, "description": "Accepted batch replay."},
        409: {"model": ErrorResponse, "description": "Batch or source conflict."},
    },
)
def import_healthkit_batch(
    body: HealthKitImportBatchRequest,
    response: Response,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> HealthKitImportBatchResult:
    try:
        result = process_healthkit_import_batch(session, owner_id, body)
    except HealthKitImportConflict as exc:
        raise APIError(409, "healthkit_import_conflict", str(exc)) from exc
    except HealthKitImportValidationError as exc:
        raise APIError(422, "healthkit_import_invalid", str(exc)) from exc
    response.status_code = 200 if result.replayed else 201
    return result


@router.get(
    "/imports/healthkit/batches/{batch_id}",
    response_model=HealthKitImportBatchResult,
    operation_id="getHealthKitBatchReceipt",
    responses={
        **COMMON_ERRORS,
        404: {"model": ErrorResponse, "description": "Import receipt was not found."},
    },
)
def get_healthkit_batch_receipt_route(
    batch_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> HealthKitImportBatchResult:
    result = get_healthkit_batch_receipt(session, owner_id, batch_id)
    if result is None:
        raise APIError(404, "healthkit_receipt_not_found", "Import receipt was not found.")
    return result


@router.get(
    "/imports/healthkit/status",
    response_model=HealthKitImportStatusResponse,
    operation_id="getHealthKitImportStatus",
    responses=COMMON_ERRORS,
)
def get_healthkit_import_status_route(
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> HealthKitImportStatusResponse:
    return get_healthkit_import_status(session, owner_id)


@router.put(
    "/imports/healthkit/source-preferences",
    response_model=HealthKitSourcePreferenceResponse,
    operation_id="setHealthKitSourcePreference",
    responses={
        **COMMON_ERRORS,
        409: {"model": ErrorResponse, "description": "Preference revision conflict."},
    },
)
def set_healthkit_source_preference_route(
    body: HealthKitSourcePreferenceRequest,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> HealthKitSourcePreferenceResponse:
    try:
        return set_healthkit_source_preference(session, owner_id, body)
    except HealthKitImportConflict as exc:
        raise APIError(409, "healthkit_preference_conflict", str(exc)) from exc
    except HealthKitImportValidationError as exc:
        raise APIError(422, "healthkit_preference_invalid", str(exc)) from exc
