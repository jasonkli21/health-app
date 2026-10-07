"""Shared HTTP dependencies for sessions, configuration and owner identity."""

from __future__ import annotations

from collections.abc import Iterator
from time import time
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from health_api.api.errors import APIError
from health_api.application.local_principal import ensure_local_principal
from health_api.application.provider_identity import resolve_provider_identity
from health_api.config.settings import Settings
from health_api.integrations.firebase_auth import (
    IdentityVerifier,
    TokenVerificationError,
    VerifierUnavailable,
)
from sqlalchemy.orm import Session

_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="FirebaseBearer",
    description="Cloud requests use a verified Firebase ID token.",
)


def get_session(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _bearer_token(value: str | None) -> str:
    if value is None or not value or len(value) > 8192 or any(char.isspace() for char in value):
        raise APIError(401, "authentication_required", "A valid bearer token is required.")
    return value


def get_current_owner(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer_scheme)] = None,
) -> UUID:
    allow_erasure_status = request.url.path == "/deletion-requests" or request.url.path.startswith(
        "/deletion-requests/"
    )
    if settings.auth_mode == "dev":
        owner_id = ensure_local_principal(
            session, settings, allow_erasure_status=allow_erasure_status
        )
        if owner_id is None:
            raise APIError(401, "principal_unavailable", "Local principal is unavailable.")
        request.state.auth_time = int(time())
        return owner_id

    token = _bearer_token(authorization.credentials if authorization is not None else None)
    verifier = cast(IdentityVerifier | None, getattr(request.app.state, "identity_verifier", None))
    if verifier is None:
        raise APIError(503, "auth_unavailable", "Identity verification is temporarily unavailable.")
    try:
        identity = verifier.verify(token)
    except TokenVerificationError:
        raise APIError(401, "invalid_token", "The bearer token is invalid or expired.") from None
    except VerifierUnavailable:
        raise APIError(
            503, "auth_unavailable", "Identity verification is temporarily unavailable."
        ) from None

    owner_id = resolve_provider_identity(
        session,
        issuer=identity.issuer,
        subject=identity.subject,
        display_timezone=settings.local_principal_timezone,
        allow_erasure_status=allow_erasure_status,
    )
    request.state.auth_time = identity.auth_time
    if owner_id is None:
        raise APIError(401, "principal_unavailable", "The authenticated account is unavailable.")
    return owner_id
