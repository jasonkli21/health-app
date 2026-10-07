"""Firebase ID-token verification with cached keys and bounded network checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from threading import BoundedSemaphore
from typing import Any, Protocol


class TokenVerificationError(Exception):
    """The bearer token is malformed, expired, revoked, or otherwise invalid."""


class VerifierUnavailable(Exception):
    """Firebase key or revocation services did not answer within their bound."""


@dataclass(frozen=True)
class VerifiedIdentity:
    issuer: str
    subject: str
    auth_time: int | None = None


class IdentityVerifier(Protocol):
    def verify(self, token: str) -> VerifiedIdentity: ...


class FirebaseTokenVerifier:
    """Use Firebase Admin SDK verification; never derive ownership from token text."""

    def __init__(self, project_id: str, *, timeout_seconds: int, max_in_flight: int) -> None:
        self.project_id = project_id
        self.timeout_seconds = timeout_seconds
        self._in_flight = BoundedSemaphore(max_in_flight)
        self._app_name = f"health-api-{project_id}"

    def verify(self, token: str) -> VerifiedIdentity:
        if len(token) > 8192 or not re.fullmatch(r"[A-Za-z0-9._~-]+", token):
            raise TokenVerificationError
        if not self._in_flight.acquire(timeout=0.2):
            raise VerifierUnavailable from None

        try:
            firebase_admin, firebase_auth = self._sdk()
            try:
                app = firebase_admin.get_app(self._app_name)
            except ValueError:
                try:
                    app = firebase_admin.initialize_app(
                        options={
                            "projectId": self.project_id,
                            "httpTimeout": self.timeout_seconds,
                        },
                        name=self._app_name,
                    )
                except ValueError:
                    # Another request may have initialized the process singleton.
                    app = firebase_admin.get_app(self._app_name)

            try:
                claims: dict[str, Any] = firebase_auth.verify_id_token(
                    token, app=app, check_revoked=True
                )
            except (
                firebase_auth.InvalidIdTokenError,
                firebase_auth.ExpiredIdTokenError,
                firebase_auth.RevokedIdTokenError,
                firebase_auth.UserDisabledError,
                firebase_auth.UserNotFoundError,
                ValueError,
            ) as exc:
                raise TokenVerificationError from exc
            except firebase_auth.CertificateFetchError as exc:
                raise VerifierUnavailable from exc
            except firebase_admin.exceptions.FirebaseError as exc:
                raise VerifierUnavailable from exc

            expected_issuer = f"https://securetoken.google.com/{self.project_id}"
            issuer = claims.get("iss")
            audience = claims.get("aud")
            subject = claims.get("sub")
            auth_time = claims.get("auth_time")
            if (
                issuer != expected_issuer
                or audience != self.project_id
                or not isinstance(subject, str)
                or not subject
                or len(subject) > 128
            ):
                raise TokenVerificationError
            if isinstance(auth_time, bool) or not isinstance(auth_time, int):
                auth_time = None
            return VerifiedIdentity(issuer=issuer, subject=subject, auth_time=auth_time)
        except (TokenVerificationError, VerifierUnavailable):
            raise
        except Exception as exc:
            # SDK credential setup and transport failures are unavailable auth, never 500s.
            raise VerifierUnavailable from exc
        finally:
            self._in_flight.release()

    @staticmethod
    def _sdk() -> tuple[Any, Any]:
        try:
            # firebase-admin has no PEP 561 typing metadata; keep the untyped SDK
            # confined to this integration boundary and validate returned claims.
            import firebase_admin  # type: ignore[import-untyped]
            from firebase_admin import auth
        except ImportError as exc:
            raise VerifierUnavailable from exc
        return firebase_admin, auth
