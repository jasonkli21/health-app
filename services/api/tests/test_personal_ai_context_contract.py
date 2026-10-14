from __future__ import annotations

import base64
import hashlib
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from health_api.api.personal_ai_context import router
from health_api.config.settings import Settings
from health_api.integrations.federation_export import HealthFederationExportRequest
from health_api.integrations.firebase_auth import (
    FirebaseTokenVerifier,
    TokenVerificationError,
    VerifiedIdentity,
)
from health_api.integrations.personal_ai_context import (
    HealthContextPayload,
    HealthContextReadRequest,
)
from health_api.integrations.personal_ai_context_auth import (
    PersonalAIContextAuthorizationError,
    PersonalAIContextIdentityVerifier,
)
from health_api.integrations.personal_ai_federation_auth import (
    PersonalAIFederationIdentityVerifier,
)

FIREBASE_PROJECT = "health-test1"
FIREBASE_ISSUER = f"https://securetoken.google.com/{FIREBASE_PROJECT}"
DELEGATION_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
DELEGATION_PUBLIC_KEY = (
    base64.urlsafe_b64encode(DELEGATION_PRIVATE_KEY.public_key().public_bytes_raw())
    .decode()
    .rstrip("=")
)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "auth_mode": "firebase",
        "firebase_project_id": FIREBASE_PROJECT,
        "personal_ai_context_read_enabled": True,
        "personal_ai_context_service_audience": "https://health.example.test",
        "personal_ai_context_service_account": "personal-ai@example.iam.gserviceaccount.com",
        "personal_ai_federation_delegation_public_key": DELEGATION_PUBLIC_KEY,
    }
    values.update(overrides)
    return Settings(**values)


class FixedIdentityVerifier(PersonalAIContextIdentityVerifier):
    def __init__(self, service_claims: dict[str, object]) -> None:
        self.service_claims = service_claims

    def _google_claims(self, token: str, audience: str) -> dict[str, object]:
        assert token == "service-token"
        assert audience == "https://health.example.test"
        return self.service_claims


class FixedFirebaseVerifier:
    def __init__(self, identity: VerifiedIdentity) -> None:
        self.identity = identity
        self.calls: list[str] = []

    def verify(self, token: str) -> VerifiedIdentity:
        self.calls.append(token)
        return self.identity


def _service_claims(**overrides: object) -> dict[str, object]:
    return {
        "iss": "https://accounts.google.com",
        "email": "personal-ai@example.iam.gserviceaccount.com",
        "email_verified": True,
        **overrides,
    }


def test_health_request_is_versioned_bounded_and_separate_from_local_preview() -> None:
    request = HealthContextReadRequest(
        operation="profile",
        category="profile_preferences",
        fields=("record", "notes"),
        max_results=4,
        max_bytes=4096,
    )
    assert request.application_id == "health"
    assert request.purpose == "personal_ai_context"
    assert request.entity_refs == ()

    with pytest.raises(ValidationError):
        HealthContextReadRequest.model_validate(
            {
                "operation": "profile",
                "category": "profile_preferences",
                "fields": ["record"],
                "owner_scope": "attacker-supplied-owner",
            }
        )
    with pytest.raises(ValidationError):
        HealthContextReadRequest(
            operation="history",
            category="nutrition",
            fields=("record",),
            window_start="2026-01-01T00:00:00Z",
            window_end="2026-05-01T00:00:00Z",
        )
    with pytest.raises(ValidationError):
        HealthContextReadRequest(
            operation="history",
            category="measurements",
            fields=("record",),
            window_start="2026-10-10T00:00:00Z",
            window_end="2026-10-11T00:00:00Z",
        )


@pytest.mark.parametrize(
    ("category", "purpose", "destination", "field"),
    (
        (
            "dietary_restrictions",
            "health_dietary_restrictions_to_travel",
            "travel",
            "dietary_restrictions",
        ),
        (
            "ergonomic_constraints",
            "health_ergonomic_constraints_to_shopping",
            "shopping",
            "ergonomic_constraints",
        ),
    ),
)
def test_health_federation_contract_accepts_only_narrow_declared_scopes(
    category: str, purpose: str, destination: str, field: str
) -> None:
    request = HealthFederationExportRequest(
        operation="read",
        category=category,
        entity_id=uuid4(),
        purpose=purpose,
        destination_application_id=destination,
        fields=(field,),
    )
    assert request.entity_type == "profile_item"
    verify = request.model_copy(update={"operation": "verify", "fields": ("permission_version",)})
    assert verify.fields == ("permission_version",)

    for changed in (
        {"destination_application_id": "shopping" if destination == "travel" else "travel"},
        {"fields": ("record",)},
        {"entity_type": "event"},
    ):
        candidate = request.model_dump()
        candidate.update(changed)
        with pytest.raises(ValidationError):
            HealthFederationExportRequest.model_validate(candidate)


def test_health_read_gate_is_independent_and_cannot_enable_assistant_messages() -> None:
    assert Settings(_env_file=None, app_env="test").personal_ai_context_read_enabled is False
    assert _settings().personal_ai_enabled is False
    with pytest.raises(
        ValidationError, match="personal_ai_context_identity_configuration_required"
    ):
        Settings(
            _env_file=None,
            app_env="test",
            personal_ai_context_read_enabled=True,
        )
    with pytest.raises(ValidationError, match="PERSONAL_AI_ENABLED cannot be true"):
        _settings(personal_ai_enabled=True)


def test_federation_export_gate_is_independent_and_defaults_off() -> None:
    assert Settings(_env_file=None, app_env="test").personal_ai_federation_export_enabled is False
    federation_only = _settings(
        personal_ai_context_read_enabled=False,
        personal_ai_federation_export_enabled=True,
    )
    assert federation_only.personal_ai_federation_export_enabled is True
    assert federation_only.personal_ai_context_read_enabled is False

    with pytest.raises(
        ValidationError, match="personal_ai_context_identity_configuration_required"
    ):
        Settings(
            _env_file=None,
            app_env="test",
            personal_ai_federation_export_enabled=True,
        )
    with pytest.raises(ValidationError, match="personal_ai_federation_delegation_key_invalid"):
        _settings(
            personal_ai_context_read_enabled=False,
            personal_ai_federation_export_enabled=True,
            personal_ai_federation_delegation_public_key="invalid",
        )


def test_dual_auth_requires_exact_google_service_and_recent_firebase_identity() -> None:
    settings = _settings()
    verifier = FixedIdentityVerifier(_service_claims())
    user_verifier = FixedFirebaseVerifier(
        VerifiedIdentity(FIREBASE_ISSUER, "firebase-subject", issued_at=int(time.time()))
    )
    identity = verifier.verify(
        service_token="service-token",
        user_token="firebase-token",
        settings=settings,
        user_verifier=user_verifier,
    )
    assert (identity.issuer, identity.subject) == (FIREBASE_ISSUER, "firebase-subject")

    for service_claims, delegated_identity in (
        (
            _service_claims(email="unexpected@example.iam.gserviceaccount.com"),
            user_verifier.identity,
        ),
        (
            _service_claims(),
            VerifiedIdentity(
                "https://accounts.google.com", "google-subject", issued_at=int(time.time())
            ),
        ),
        (
            _service_claims(),
            VerifiedIdentity(FIREBASE_ISSUER, "firebase-subject", issued_at=int(time.time()) - 601),
        ),
    ):
        with pytest.raises(PersonalAIContextAuthorizationError):
            FixedIdentityVerifier(service_claims).verify(
                service_token="service-token",
                user_token="firebase-token",
                settings=settings,
                user_verifier=FixedFirebaseVerifier(delegated_identity),
            )


@pytest.mark.asyncio
async def test_invalid_owner_identity_is_rejected_before_opening_a_database_session() -> None:
    app = FastAPI()
    app.state.settings = _settings()
    app.state.identity_verifier = FixedFirebaseVerifier(
        VerifiedIdentity(FIREBASE_ISSUER, "unused", issued_at=int(time.time()))
    )

    class RejectingVerifier:
        def verify(self, **kwargs: object) -> None:
            del kwargs
            raise PersonalAIContextAuthorizationError("owner identity not mapped")

    app.state.personal_ai_context_identity_verifier = RejectingVerifier()

    def session_factory() -> None:
        raise AssertionError("unauthorized requests must not open a Health data session")

    app.state.session_factory = session_factory
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/v1/integrations/personal-ai/context",
            headers={
                "Authorization": "Bearer service-token",
                "X-User-ID-Token": "invalid-or-unmapped-user-token",
            },
            json={"operation": "catalog"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_federation_owner_is_rejected_before_opening_a_database_session() -> None:
    app = FastAPI()
    app.state.settings = _settings(
        personal_ai_context_read_enabled=False,
        personal_ai_federation_export_enabled=True,
    )
    app.state.identity_verifier = FixedFirebaseVerifier(
        VerifiedIdentity(FIREBASE_ISSUER, "unused", issued_at=int(time.time()))
    )

    class RejectingVerifier:
        def verify(self, **kwargs: object) -> None:
            del kwargs
            raise PersonalAIContextAuthorizationError("owner identity not mapped")

    app.state.personal_ai_federation_identity_verifier = RejectingVerifier()

    def session_factory() -> None:
        raise AssertionError("unauthorized requests must not open a Health data session")

    app.state.session_factory = session_factory
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/v1/integrations/personal-ai/federation-export",
            headers={
                "Authorization": "Bearer service-token",
                "X-Personal-AI-User-Delegation": "invalid-or-unmapped-delegation",
            },
            json={
                "operation": "read",
                "category": "dietary_restrictions",
                "entity_id": str(uuid4()),
                "purpose": "health_dietary_restrictions_to_travel",
                "destination_application_id": "travel",
                "fields": ["dietary_restrictions"],
            },
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_federation_only_gate_keeps_the_broad_context_route_closed() -> None:
    app = FastAPI()
    app.state.settings = _settings(
        personal_ai_context_read_enabled=False,
        personal_ai_federation_export_enabled=True,
    )
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/v1/integrations/personal-ai/context",
            json={"operation": "catalog"},
        )
    assert response.status_code == 404


def test_request_cannot_use_a_profile_item_reference_for_another_object_type() -> None:
    with pytest.raises(ValidationError):
        HealthContextReadRequest(
            operation="profile",
            category="profile_background",
            entity_refs=(("event", uuid4()),),
            fields=("record",),
        )


def test_projection_allows_omitted_daily_domain_but_checks_selected_domain() -> None:
    projected = HealthContextPayload(category="nutrition", object_type="event")
    assert projected.domain is None

    with pytest.raises(ValidationError, match="health_context_daily_domain_mismatch"):
        HealthContextPayload(category="nutrition", object_type="event", domain="exercise")


def test_projection_rejects_custom_tracker_values_outside_the_shared_schema() -> None:
    with pytest.raises(ValidationError, match="health_context_daily_payload_invalid"):
        HealthContextPayload(
            category="measurements",
            object_type="observation",
            domain="measurements",
            record={
                "value": {
                    "metric": "custom",
                    "tracker_id": str(uuid4()),
                    "schema_version": 1,
                    "values": {"value": 1},
                }
            },
        )


def _signed_delegation(request_body: dict[str, object], **claim_overrides: object) -> str:
    now = int(time.time())
    request_bytes = json.dumps(
        request_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    header = {"alg": "EdDSA", "kid": "health-federation-v1", "typ": "JWT"}
    claims: dict[str, object] = {
        "iss": "personal-ai-system",
        "aud": "https://health.example.test",
        "sub": "https://accounts.google.com|google-user-1",
        "user_issuer": "https://accounts.google.com",
        "user_subject": "google-user-1",
        "iat": now,
        "exp": now + 30,
        "auth_time": now,
        "jti": str(uuid4()),
        "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
        "purpose": request_body["purpose"],
        "destination_application_id": request_body["destination_application_id"],
        **claim_overrides,
    }

    def encode(value: object) -> str:
        return (
            base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode())
            .decode()
            .rstrip("=")
        )

    signing_input = f"{encode(header)}.{encode(claims)}"
    signature = (
        base64.urlsafe_b64encode(DELEGATION_PRIVATE_KEY.sign(signing_input.encode("ascii")))
        .decode()
        .rstrip("=")
    )
    return f"{signing_input}.{signature}"


def _federation_body() -> dict[str, object]:
    return {
        "schema_version": "health-federation-export-v1",
        "application_id": "health",
        "workspace_id": None,
        "operation": "read",
        "category": "dietary_restrictions",
        "entity_type": "profile_item",
        "entity_id": str(uuid4()),
        "purpose": "health_dietary_restrictions_to_travel",
        "destination_application_id": "travel",
        "fields": ["dietary_restrictions"],
        "max_bytes": 4096,
    }


def test_signed_delegation_binds_google_user_service_audience_and_exact_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(personal_ai_federation_export_enabled=True)
    monkeypatch.setattr(
        PersonalAIContextIdentityVerifier,
        "_google_claims",
        staticmethod(
            lambda token, audience: (
                _service_claims()
                if token == "service-token"
                and audience == settings.personal_ai_context_service_audience
                else {}
            )
        ),
    )
    body = _federation_body()
    delegation = _signed_delegation(body)
    identity = PersonalAIFederationIdentityVerifier().verify(
        service_token="service-token",
        delegation=delegation,
        request_body=body,
        settings=settings,
    )
    assert identity.issuer == "https://accounts.google.com"
    assert identity.subject == "google-user-1"
    assert identity.authenticated_at is not None
    encoded_claims = delegation.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(encoded_claims + "=" * (-len(encoded_claims) % 4)))
    assert identity.authenticated_at == claims["auth_time"]


@pytest.mark.parametrize(
    ("changes", "tamper"),
    [
        ({"aud": "wrong-service"}, False),
        ({"exp": int(time.time()) - 1}, False),
        ({"auth_time": int(time.time()) - 601}, False),
        ({"auth_time": int(time.time()) + 61}, False),
        ({}, True),
    ],
)
def test_signed_delegation_rejects_wrong_audience_expiry_stale_auth_and_bad_signature(
    monkeypatch: pytest.MonkeyPatch,
    changes: dict[str, object],
    tamper: bool,
) -> None:
    settings = _settings(personal_ai_federation_export_enabled=True)
    monkeypatch.setattr(
        PersonalAIContextIdentityVerifier,
        "_google_claims",
        staticmethod(lambda _token, _audience: _service_claims()),
    )
    body = _federation_body()
    assertion = _signed_delegation(body, **changes)
    if tamper:
        header, claims, signature = assertion.split(".")
        signature = ("A" if signature[0] != "A" else "B") + signature[1:]
        assertion = f"{header}.{claims}.{signature}"
    with pytest.raises(PersonalAIContextAuthorizationError):
        PersonalAIFederationIdentityVerifier().verify(
            service_token="service-token",
            delegation=assertion,
            request_body=body,
            settings=settings,
        )


def test_signed_delegation_rejects_user_shaped_unsigned_or_unbound_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(personal_ai_federation_export_enabled=True)
    monkeypatch.setattr(
        PersonalAIContextIdentityVerifier,
        "_google_claims",
        staticmethod(lambda _token, _audience: _service_claims()),
    )
    body = _federation_body()
    verifier = PersonalAIFederationIdentityVerifier()
    with pytest.raises(PersonalAIContextAuthorizationError):
        verifier.verify(
            service_token="service-token",
            delegation="",
            request_body=body,
            settings=settings,
        )
    with pytest.raises(PersonalAIContextAuthorizationError):
        verifier.verify(
            service_token="service-token",
            delegation=_signed_delegation(body),
            request_body={**body, "entity_id": str(uuid4())},
            settings=settings,
        )


def test_firebase_google_identity_mapping_requires_an_active_linked_provider() -> None:
    class FakeFirebaseAuth:
        UserNotFoundError = type("UserNotFoundError", (Exception,), {})
        UserDisabledError = type("UserDisabledError", (Exception,), {})

        def __init__(self, user: object) -> None:
            self.user = user
            self.lookup: tuple[str, str] | None = None

        def get_user_by_provider_uid(self, provider_id: str, provider_uid: str, *, app: object):
            del app
            self.lookup = (provider_id, provider_uid)
            return self.user

    class FakeFirebaseAdmin:
        exceptions = SimpleNamespace(FirebaseError=type("FirebaseError", (Exception,), {}))

        @staticmethod
        def get_app(_name: str) -> object:
            return object()

    linked = SimpleNamespace(
        disabled=False,
        uid="firebase-owner-uid",
        provider_data=[SimpleNamespace(provider_id="google.com", uid="google-user-1")],
    )
    verifier = FirebaseTokenVerifier(FIREBASE_PROJECT, timeout_seconds=1, max_in_flight=1)
    fake_auth = FakeFirebaseAuth(linked)
    verifier._sdk = lambda: (FakeFirebaseAdmin, fake_auth)  # type: ignore[method-assign]
    assert verifier.resolve_google_provider_uid("google-user-1") == "firebase-owner-uid"
    assert fake_auth.lookup == ("google.com", "google-user-1")

    fake_auth.user = SimpleNamespace(
        disabled=False,
        uid="firebase-owner-uid",
        provider_data=[SimpleNamespace(provider_id="password", uid="google-user-1")],
    )
    with pytest.raises(TokenVerificationError):
        verifier.resolve_google_provider_uid("google-user-1")
