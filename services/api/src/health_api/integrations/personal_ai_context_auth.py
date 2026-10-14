"""Separate caller-service and delegated Firebase owner verification."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from health_api.config.settings import Settings
from health_api.integrations.firebase_auth import (
    IdentityVerifier,
    TokenVerificationError,
    VerifierUnavailable,
)

GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})


class PersonalAIContextAuthorizationError(ValueError):
    """Stable rejection that does not reveal whether a Health owner exists."""


@dataclass(frozen=True)
class VerifiedPersonalAIContextIdentity:
    issuer: str
    subject: str


def _bounded_google_request_type() -> Callable[[], Any]:
    from google.auth.transport.requests import Request

    class BoundedGoogleRequest(Request):
        def __call__(
            self,
            url: str,
            method: str = "GET",
            body: bytes | None = None,
            headers: Mapping[str, str] | None = None,
            timeout: float | None = 3,
            **kwargs: Any,
        ) -> Any:
            request = cast(Callable[..., Any], super().__call__)
            return request(
                url,
                method=method,
                body=body,
                headers=headers,
                timeout=min(timeout or 3, 3),
                **kwargs,
            )

    return cast(Callable[[], Any], BoundedGoogleRequest)


class PersonalAIContextIdentityVerifier:
    """Verify an exact Personal AI caller and a recent, revoked-checked Firebase user token."""

    def verify(
        self,
        *,
        service_token: str,
        user_token: str,
        settings: Settings,
        user_verifier: IdentityVerifier,
    ) -> VerifiedPersonalAIContextIdentity:
        if not settings.personal_ai_context_read_enabled:
            raise PersonalAIContextAuthorizationError("personal_ai_context_disabled")
        if (
            not service_token
            or not user_token
            or len(service_token) > 8192
            or len(user_token) > 8192
        ):
            raise PersonalAIContextAuthorizationError("personal_ai_context_identity_invalid")

        service_claims = self._google_claims(
            service_token, settings.personal_ai_context_service_audience
        )
        if (
            service_claims.get("email") != settings.personal_ai_context_service_account
            or service_claims.get("email_verified") is not True
        ):
            raise PersonalAIContextAuthorizationError("personal_ai_context_caller_denied")

        try:
            identity = user_verifier.verify(user_token)
        except TokenVerificationError as error:
            raise PersonalAIContextAuthorizationError("personal_ai_context_user_denied") from error
        except VerifierUnavailable as error:
            raise PersonalAIContextAuthorizationError(
                "personal_ai_context_identity_unavailable"
            ) from error

        now = int(time.time())
        if (
            identity.issuer != f"https://securetoken.google.com/{settings.firebase_project_id}"
            or not identity.subject
            or identity.issued_at is None
            or identity.issued_at > now + 30
            or now - identity.issued_at > settings.personal_ai_context_user_token_max_age_seconds
        ):
            raise PersonalAIContextAuthorizationError("personal_ai_context_user_denied")
        return VerifiedPersonalAIContextIdentity(
            issuer=identity.issuer,
            subject=identity.subject,
        )

    @staticmethod
    def _google_claims(token: str, audience: str) -> dict[str, Any]:
        try:
            from google.oauth2.id_token import verify_oauth2_token

            request = _bounded_google_request_type()()
            verifier = cast(Callable[..., dict[str, Any]], verify_oauth2_token)
            claims = verifier(
                token,
                request,
                audience=audience,
                clock_skew_in_seconds=30,
            )
        except Exception as error:  # Google verifier errors can contain token material.
            raise PersonalAIContextAuthorizationError(
                "personal_ai_context_identity_invalid"
            ) from error
        finally:
            if "request" in locals():
                request.session.close()
        if not isinstance(claims, dict) or claims.get("iss") not in GOOGLE_ISSUERS:
            raise PersonalAIContextAuthorizationError("personal_ai_context_identity_invalid")
        return claims
