"""Default-off Health read endpoint for Personal AI's typed context contract."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from health_api.application.personal_ai_context import (
    HealthContextSelectionError,
    read_personal_ai_health_context,
    resolve_existing_owner,
)
from health_api.integrations.personal_ai_context import (
    HEALTH_CONTEXT_PATH,
    HealthContextReadRequest,
    HealthContextReadResponse,
)
from health_api.integrations.personal_ai_context_auth import (
    PersonalAIContextAuthorizationError,
    PersonalAIContextIdentityVerifier,
)

router = APIRouter(tags=["Personal AI Health context"])
MAX_REQUEST_BYTES = 8_192


async def _bounded_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdecimal() and int(declared) > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="Request is too large")
    body = bytearray()
    async for block in request.stream():
        body.extend(block)
        if len(body) > MAX_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="Request is too large")
    return bytes(body)


@router.post(
    HEALTH_CONTEXT_PATH,
    operation_id="readPersonalAIHealthContext",
    response_model=HealthContextReadResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": HealthContextReadRequest.model_json_schema()
                }
            },
        }
    },
)
async def read_health_context(request: Request) -> Response:
    settings = request.app.state.settings
    if not settings.personal_ai_context_read_enabled:
        raise HTTPException(status_code=404, detail="Not found")

    service_headers = request.headers.getlist("authorization")
    user_headers = request.headers.getlist("x-user-id-token")
    if len(service_headers) != 1 or len(user_headers) != 1:
        raise HTTPException(status_code=401, detail="Authentication required")
    scheme, separator, service_token = service_headers[0].partition(" ")
    if scheme.casefold() != "bearer" or not separator or not service_token.strip():
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        raw = await _bounded_body(request)
        body = HealthContextReadRequest.model_validate_json(raw)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=422, detail="Invalid Health context request") from error

    user_verifier = getattr(request.app.state, "identity_verifier", None)
    # Protocol instances are not runtime-checkable; validate the injected boundary by shape.
    if user_verifier is None or not callable(getattr(user_verifier, "verify", None)):
        raise HTTPException(status_code=503, detail="Identity service unavailable")
    verifier = getattr(
        request.app.state,
        "personal_ai_context_identity_verifier",
        PersonalAIContextIdentityVerifier(),
    )
    try:
        identity = await run_in_threadpool(
            verifier.verify,
            service_token=service_token.strip(),
            user_token=user_headers[0],
            settings=settings,
            user_verifier=user_verifier,
        )
    except PersonalAIContextAuthorizationError as error:
        raise HTTPException(status_code=401, detail="Authentication required") from error

    session_factory = request.app.state.session_factory
    try:
        with session_factory() as session, session.begin():
            if session.get_bind().dialect.name == "postgresql":
                session.execute(text("SET TRANSACTION READ ONLY"))
                session.execute(text("SET LOCAL statement_timeout = '1800ms'"))
            owner_id = resolve_existing_owner(
                session,
                issuer=identity.issuer,
                subject=identity.subject,
            )
            if owner_id is None:
                raise HTTPException(status_code=401, detail="Authentication required")
            result = read_personal_ai_health_context(session, owner_id, body)
            encoded = result.model_dump_json().encode("utf-8")
            if len(encoded) > body.max_bytes:
                raise HTTPException(status_code=413, detail="Response is too large")
    except HTTPException:
        raise
    except HealthContextSelectionError as error:
        if str(error) == "health_context_response_limit_exceeded":
            raise HTTPException(status_code=413, detail="Response is too large") from error
        raise HTTPException(status_code=422, detail="Health context selection is invalid") from error
    except SQLAlchemyError:
        raise
    return Response(
        content=encoded,
        status_code=status.HTTP_200_OK,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )
