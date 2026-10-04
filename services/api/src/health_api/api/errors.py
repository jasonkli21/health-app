"""Stable, privacy-safe API exception responses."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from health_api.api.schemas import ErrorResponse, FieldError
from health_api.application.errors import (
    DailyConflict,
    DailyNotFound,
    DailySnapshotLimitExceeded,
    DailyValidationError,
    ProfileConflict,
    ProfileNotFound,
    ProfileValidationError,
)
from sqlalchemy.exc import SQLAlchemyError

_SAFE_FIELD_NAMES = {
    "id",
    "profile",
    "kind",
    "category",
    "key",
    "label",
    "value",
    "type",
    "unit",
    "notes",
    "metadata",
    "valid_from",
    "valid_to",
    "ai_use_allowed",
    "cross_domain_use_allowed",
    "expected_revision",
    "as_of",
    "after_revision",
    "limit",
    "cursor",
    "item_id",
    "event",
    "observation",
    "domain",
    "time",
    "occurred_at",
    "ended_at",
    "interval_end",
    "metric",
    "timezone",
    "local_date",
    "event_id",
    "observation_id",
    "objects",
    "links",
}


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unavailable"))


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    field_errors: list[FieldError] | None = None,
) -> JSONResponse:
    content = ErrorResponse(
        code=code,
        message=message,
        field_errors=field_errors,
        request_id=_request_id(request),
    ).model_dump(mode="json")
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers={"X-Request-ID": _request_id(request)},
    )


def _field_errors(errors: Sequence[dict[str, Any]]) -> list[FieldError]:
    result: list[FieldError] = []
    for error in errors:
        location = [
            str(part)
            for part in error.get("loc", ())
            if part in _SAFE_FIELD_NAMES or isinstance(part, int)
        ]
        result.append(
            FieldError(
                field=".".join(location) or "request",
                message="Invalid or missing value.",
            )
        )
    return result


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        return _error_response(request, exc.status_code, exc.code, exc.message)

    @app.exception_handler(ProfileNotFound)
    async def not_found_handler(request: Request, _exc: ProfileNotFound) -> JSONResponse:
        return _error_response(request, 404, "not_found", "Profile item was not found.")

    @app.exception_handler(ProfileConflict)
    async def conflict_handler(request: Request, exc: ProfileConflict) -> JSONResponse:
        return _error_response(request, 409, "conflict", str(exc) or "Profile update conflict.")

    @app.exception_handler(ProfileValidationError)
    async def profile_validation_handler(
        request: Request, _exc: ProfileValidationError
    ) -> JSONResponse:
        return _error_response(request, 422, "validation_error", "Profile data is invalid.")

    @app.exception_handler(DailyNotFound)
    async def daily_not_found_handler(request: Request, _exc: DailyNotFound) -> JSONResponse:
        return _error_response(request, 404, "not_found", "Daily entry was not found.")

    @app.exception_handler(DailyConflict)
    async def daily_conflict_handler(request: Request, exc: DailyConflict) -> JSONResponse:
        return _error_response(request, 409, "conflict", str(exc) or "Daily entry conflict.")

    @app.exception_handler(DailyValidationError)
    async def daily_validation_handler(
        request: Request, _exc: DailyValidationError
    ) -> JSONResponse:
        return _error_response(request, 422, "validation_error", "Daily entry is invalid.")

    @app.exception_handler(DailySnapshotLimitExceeded)
    async def daily_snapshot_limit_handler(
        request: Request, _exc: DailySnapshotLimitExceeded
    ) -> JSONResponse:
        return _error_response(
            request,
            422,
            "today_window_too_large",
            "The selected day has too many entries for a safe Today snapshot.",
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            request,
            422,
            "validation_error",
            "Request validation failed.",
            _field_errors(exc.errors()),
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request: Request, _exc: SQLAlchemyError) -> JSONResponse:
        return _error_response(
            request,
            503,
            "service_unavailable",
            "Health storage is temporarily unavailable.",
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, _exc: Exception) -> JSONResponse:
        return _error_response(
            request, 500, "internal_error", "The request could not be completed."
        )
