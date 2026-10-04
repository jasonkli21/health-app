from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from health_api.integrations.firebase_auth import (
    FirebaseTokenVerifier,
    TokenVerificationError,
    VerifierUnavailable,
)


class InvalidIdTokenError(Exception):
    pass


class ExpiredIdTokenError(Exception):
    pass


class RevokedIdTokenError(Exception):
    pass


class UserDisabledError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class CertificateFetchError(Exception):
    pass


class FirebaseError(Exception):
    pass


class FakeFirebaseAdmin:
    exceptions = SimpleNamespace(FirebaseError=FirebaseError)

    def __init__(self) -> None:
        self.app = object()
        self.options: dict[str, object] | None = None
        self.name: str | None = None

    def get_app(self, _name: str) -> object:
        raise ValueError("not initialized")

    def initialize_app(self, *, options: dict[str, object], name: str) -> object:
        self.options = options
        self.name = name
        return self.app


class FakeFirebaseAuth:
    InvalidIdTokenError = InvalidIdTokenError
    ExpiredIdTokenError = ExpiredIdTokenError
    RevokedIdTokenError = RevokedIdTokenError
    UserDisabledError = UserDisabledError
    UserNotFoundError = UserNotFoundError
    CertificateFetchError = CertificateFetchError

    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, object, bool]] = []

    def verify_id_token(self, token: str, *, app: object, check_revoked: bool) -> dict[str, Any]:
        self.calls.append((token, app, check_revoked))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _wire_sdk(
    monkeypatch: pytest.MonkeyPatch,
    result: dict[str, Any] | Exception,
) -> tuple[FakeFirebaseAdmin, FakeFirebaseAuth, FirebaseTokenVerifier]:
    admin = FakeFirebaseAdmin()
    auth = FakeFirebaseAuth(result)
    verifier = FirebaseTokenVerifier("health-prod-1234", timeout_seconds=4, max_in_flight=2)
    monkeypatch.setattr(verifier, "_sdk", lambda: (admin, auth))
    return admin, auth, verifier


def test_verifier_checks_revocation_and_uses_bounded_sdk_http_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims = {
        "iss": "https://securetoken.google.com/health-prod-1234",
        "aud": "health-prod-1234",
        "sub": "firebase-subject-123",
    }
    admin, auth, verifier = _wire_sdk(monkeypatch, claims)

    identity = verifier.verify("header.payload.signature")

    assert identity.issuer == claims["iss"]
    assert identity.subject == claims["sub"]
    assert auth.calls == [("header.payload.signature", admin.app, True)]
    assert admin.options == {"projectId": "health-prod-1234", "httpTimeout": 4}


@pytest.mark.parametrize(
    "failure",
    [
        InvalidIdTokenError(),
        ExpiredIdTokenError(),
        RevokedIdTokenError(),
        UserDisabledError(),
        UserNotFoundError(),
    ],
)
def test_invalid_expired_revoked_and_disabled_tokens_fail_as_401(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    _, _, verifier = _wire_sdk(monkeypatch, failure)
    with pytest.raises(TokenVerificationError):
        verifier.verify("header.payload.signature")


@pytest.mark.parametrize("failure", [CertificateFetchError(), FirebaseError("unavailable")])
def test_key_or_revocation_service_outage_fails_closed_as_unavailable(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    _, _, verifier = _wire_sdk(monkeypatch, failure)
    with pytest.raises(VerifierUnavailable):
        verifier.verify("header.payload.signature")


@pytest.mark.parametrize(
    "claims",
    [
        {
            "iss": "https://securetoken.google.com/other-project",
            "aud": "health-prod-1234",
            "sub": "u",
        },
        {
            "iss": "https://securetoken.google.com/health-prod-1234",
            "aud": "other-project",
            "sub": "u",
        },
        {
            "iss": "https://securetoken.google.com/health-prod-1234",
            "aud": "health-prod-1234",
            "sub": "",
        },
    ],
)
def test_claims_must_bind_to_expected_project_and_subject(
    monkeypatch: pytest.MonkeyPatch, claims: dict[str, Any]
) -> None:
    _, _, verifier = _wire_sdk(monkeypatch, claims)
    with pytest.raises(TokenVerificationError):
        verifier.verify("header.payload.signature")


def test_malformed_or_overlong_tokens_do_not_call_the_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, auth, verifier = _wire_sdk(monkeypatch, {})
    with pytest.raises(TokenVerificationError):
        verifier.verify("header.payload.signature=")
    with pytest.raises(TokenVerificationError):
        verifier.verify("x" * 8193)
    assert auth.calls == []


def test_verifier_saturation_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, verifier = _wire_sdk(monkeypatch, {})
    verifier._in_flight.acquire()
    verifier._in_flight.acquire()
    try:
        with pytest.raises(VerifierUnavailable):
            verifier.verify("header.payload.signature")
    finally:
        verifier._in_flight.release()
        verifier._in_flight.release()
