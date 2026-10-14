"""Bind recent verified Firebase authentication to an existing linked Google account."""

import base64
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from health_api.application.personal_ai_context import resolve_existing_owner
from health_api.integrations.firebase_auth import TokenVerificationError, VerifierUnavailable
from health_api.integrations.personal_ai_context_auth import PersonalAIContextIdentityVerifier
from health_api.integrations.task_wire import verify_delegated_user


@dataclass(frozen=True)
class GoogleTaskPrincipal:
    issuer: str
    subject: str
    authenticated_at: int


def _linked_owner(
    request: Request, session: Session, google_subject: str, authenticated_at: int
) -> tuple[str, UUID]:
    verifier = getattr(request.app.state, "identity_verifier", None)
    resolver = getattr(verifier, "resolve_google_delegation", None)
    if not callable(resolver):
        raise HTTPException(503, "task_identity_unavailable")
    try:
        firebase_uid = resolver(google_subject, authenticated_at)
    except TokenVerificationError as error:
        raise HTTPException(401, "task_identity_denied") from error
    except VerifierUnavailable as error:
        raise HTTPException(503, "task_identity_unavailable") from error
    issuer = f"https://securetoken.google.com/{request.app.state.settings.firebase_project_id}"
    owner_id = resolve_existing_owner(session, issuer=issuer, subject=firebase_uid)
    if owner_id is None:
        raise HTTPException(401, "task_identity_denied")
    return firebase_uid, owner_id


def source_principal(request: Request, session: Session, owner_id: UUID) -> GoogleTaskPrincipal:
    settings = request.app.state.settings
    if settings.task_control is None or settings.auth_mode != "firebase":
        raise HTTPException(404, "not_found")
    identity = getattr(request.state, "verified_identity", None)
    auth_time = getattr(identity, "auth_time", None)
    if (
        identity is None
        or type(auth_time) is not int
        or not -30 <= int(time.time()) - auth_time <= 300
    ):
        raise HTTPException(401, "recent_authentication_required")
    uid, linked_owner = _linked_owner(request, session, settings.task_google_subject, auth_time)
    if uid != identity.subject or linked_owner != owner_id:
        raise HTTPException(401, "task_identity_denied")
    return GoogleTaskPrincipal(
        "https://accounts.google.com", settings.task_google_subject, auth_time
    )


def incoming_owner(request: Request, session: Session, body: dict[str, Any]) -> UUID:
    settings, task = request.app.state.settings, request.app.state.settings.task_control
    if task is None:
        raise HTTPException(404, "not_found")
    try:
        auth, assertions = (
            request.headers.getlist("authorization"),
            request.headers.getlist("x-user-delegation"),
        )
        if len(auth) != 1 or len(assertions) != 1 or not auth[0].startswith("Bearer "):
            raise ValueError
        verifier = getattr(
            request.app.state,
            "task_service_verifier",
            PersonalAIContextIdentityVerifier._google_claims,
        )
        claims = verifier(auth[0][7:], settings.personal_ai_context_service_audience)
        if (
            claims.get("email") != settings.personal_ai_context_service_account
            or claims.get("email_verified") is not True
        ):
            raise ValueError
        identity = verify_delegated_user(
            assertions[0],
            body,
            public_key=Ed25519PublicKey.from_public_bytes(
                base64.b64decode(
                    task.pai_public_key + "=" * (-len(task.pai_public_key) % 4),
                    altchars=b"-_",
                    validate=True,
                )
            ),
            issuer=task.pai_issuer,
            audience=settings.personal_ai_context_service_audience,
            key_id=task.pai_key_id,
            now=int(time.time()),
            allowed_user_issuers=frozenset({"https://accounts.google.com"}),
        )
        if identity.subject != settings.task_google_subject:
            raise ValueError
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(401, "task_identity_denied") from error
    return _linked_owner(request, session, identity.subject, identity.authenticated_at)[1]
