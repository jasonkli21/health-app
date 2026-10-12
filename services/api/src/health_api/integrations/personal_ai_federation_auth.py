"""Verify short-lived Personal AI delegated-user assertions for Health exports."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from health_api.config.settings import Settings
from health_api.integrations.personal_ai_context_auth import (
    GOOGLE_ISSUERS,
    PersonalAIContextAuthorizationError,
    PersonalAIContextIdentityVerifier,
)


@dataclass(frozen=True)
class VerifiedDelegatedGoogleIdentity:
    issuer: str
    subject: str


class PersonalAIFederationIdentityVerifier:
    """Verify both the exact Personal AI service and a request-bound user assertion."""

    @staticmethod
    def _decode_segment(value: str) -> bytes:
        if not value or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=" for character in value):
            raise PersonalAIContextAuthorizationError("personal_ai_delegation_invalid")
        try:
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        except (ValueError, TypeError) as error:
            raise PersonalAIContextAuthorizationError("personal_ai_delegation_invalid") from error

    def verify(
        self,
        *,
        service_token: str,
        delegation: str,
        request_body: dict[str, Any],
        settings: Settings,
    ) -> VerifiedDelegatedGoogleIdentity:
        if (
            not settings.personal_ai_federation_export_enabled
            or not service_token
            or len(service_token) > 8192
            or not delegation
            or len(delegation) > 8192
        ):
            raise PersonalAIContextAuthorizationError("personal_ai_delegation_invalid")

        service_claims = PersonalAIContextIdentityVerifier._google_claims(
            service_token, settings.personal_ai_context_service_audience
        )
        if (
            service_claims.get("email") != settings.personal_ai_context_service_account
            or service_claims.get("email_verified") is not True
        ):
            raise PersonalAIContextAuthorizationError("personal_ai_context_caller_denied")

        segments = delegation.split(".")
        if len(segments) != 3:
            raise PersonalAIContextAuthorizationError("personal_ai_delegation_invalid")
        header_bytes, claims_bytes, signature = (
            self._decode_segment(segment) for segment in segments
        )
        try:
            header = json.loads(header_bytes)
            claims = json.loads(claims_bytes)
            encoded_public_key = settings.personal_ai_federation_delegation_public_key.strip()
            public_bytes = self._decode_segment(encoded_public_key)
            public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
            public_key.verify(
                signature,
                f"{segments[0]}.{segments[1]}".encode("ascii"),
            )
        except (ValueError, TypeError, json.JSONDecodeError, InvalidSignature) as error:
            raise PersonalAIContextAuthorizationError("personal_ai_delegation_invalid") from error

        if (
            not isinstance(header, dict)
            or header != {
                "alg": "EdDSA",
                "kid": settings.personal_ai_federation_delegation_key_id,
                "typ": "JWT",
            }
            or not isinstance(claims, dict)
        ):
            raise PersonalAIContextAuthorizationError("personal_ai_delegation_invalid")
        required = {
            "iss",
            "aud",
            "sub",
            "user_issuer",
            "user_subject",
            "iat",
            "exp",
            "auth_time",
            "jti",
            "request_sha256",
            "purpose",
            "destination_application_id",
        }
        if set(claims) != required:
            raise PersonalAIContextAuthorizationError("personal_ai_delegation_invalid")

        now = int(time.time())
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        authenticated_at = claims.get("auth_time")
        issuer = claims.get("user_issuer")
        subject = claims.get("user_subject")
        try:
            UUID(claims.get("jti"))
            request_bytes = json.dumps(
                request_body,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        except (ValueError, TypeError, AttributeError) as error:
            raise PersonalAIContextAuthorizationError("personal_ai_delegation_invalid") from error
        if (
            claims.get("iss") != settings.personal_ai_federation_delegation_issuer
            or claims.get("aud") != settings.personal_ai_context_service_audience
            or not isinstance(issuer, str)
            or issuer not in GOOGLE_ISSUERS
            or not isinstance(subject, str)
            or not subject
            or len(subject) > 128
            or claims.get("sub") != f"{issuer}|{subject}"
            or isinstance(issued_at, bool)
            or not isinstance(issued_at, int)
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, int)
            or isinstance(authenticated_at, bool)
            or not isinstance(authenticated_at, int)
            or issued_at > now + 30
            or expires_at <= now
            or expires_at <= issued_at
            or expires_at - issued_at > 60
            or now - issued_at > 60
            or authenticated_at > now + 30
            or now - authenticated_at
            > settings.personal_ai_context_user_token_max_age_seconds
            or claims.get("request_sha256") != hashlib.sha256(request_bytes).hexdigest()
            or claims.get("purpose") != request_body.get("purpose")
            or claims.get("destination_application_id")
            != request_body.get("destination_application_id")
        ):
            raise PersonalAIContextAuthorizationError("personal_ai_delegation_invalid")
        return VerifiedDelegatedGoogleIdentity(issuer=issuer, subject=subject)
