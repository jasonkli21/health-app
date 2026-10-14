"""Health's policy adapter around the canonical request-bound delegated-user verifier."""

import base64
import time
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from health_api.config.settings import Settings
from health_api.integrations.personal_ai_context_auth import (
    GOOGLE_ISSUERS,
    PersonalAIContextAuthorizationError,
    PersonalAIContextIdentityVerifier,
)
from health_api.integrations.task_wire import verify_delegated_user


@dataclass(frozen=True)
class VerifiedDelegatedGoogleIdentity:
    issuer: str
    subject: str
    authenticated_at: int | None = None


class PersonalAIFederationIdentityVerifier:
    """Keep current IAM, Health recency and linked-owner policy; share JWT semantics."""

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
        ):
            raise PersonalAIContextAuthorizationError("personal_ai_delegation_invalid")
        try:
            claims = PersonalAIContextIdentityVerifier._google_claims(
                service_token, settings.personal_ai_context_service_audience
            )
            if (
                claims.get("email") != settings.personal_ai_context_service_account
                or claims.get("email_verified") is not True
            ):
                raise ValueError
            encoded = settings.personal_ai_federation_delegation_public_key
            identity = verify_delegated_user(
                delegation,
                request_body,
                public_key=Ed25519PublicKey.from_public_bytes(
                    base64.b64decode(
                        encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
                    )
                ),
                issuer=settings.personal_ai_federation_delegation_issuer,
                audience=settings.personal_ai_context_service_audience,
                key_id=settings.personal_ai_federation_delegation_key_id,
                now=int(time.time()),
                allowed_user_issuers=GOOGLE_ISSUERS,
                max_auth_age_seconds=min(
                    settings.personal_ai_context_user_token_max_age_seconds, 300
                ),
            )
            return VerifiedDelegatedGoogleIdentity(
                identity.issuer, identity.subject, identity.authenticated_at
            )
        except Exception as error:
            raise PersonalAIContextAuthorizationError("personal_ai_delegation_invalid") from error
