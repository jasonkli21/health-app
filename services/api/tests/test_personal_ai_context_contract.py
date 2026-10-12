from __future__ import annotations

import time
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from health_api.api.personal_ai_context import router
from health_api.config.settings import Settings
from health_api.integrations.federation_export import HealthFederationExportRequest
from health_api.integrations.firebase_auth import VerifiedIdentity
from health_api.integrations.personal_ai_context import (
    HealthContextPayload,
    HealthContextReadRequest,
)
from health_api.integrations.personal_ai_context_auth import (
    PersonalAIContextAuthorizationError,
    PersonalAIContextIdentityVerifier,
)

FIREBASE_PROJECT = "health-test1"
FIREBASE_ISSUER = f"https://securetoken.google.com/{FIREBASE_PROJECT}"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "auth_mode": "firebase",
        "firebase_project_id": FIREBASE_PROJECT,
        "personal_ai_context_read_enabled": True,
        "personal_ai_context_service_audience": "https://health.example.test",
        "personal_ai_context_service_account": "personal-ai@example.iam.gserviceaccount.com",
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
    with pytest.raises(ValidationError, match="personal_ai_context_identity_configuration_required"):
        Settings(
            _env_file=None,
            app_env="test",
            personal_ai_context_read_enabled=True,
        )
    with pytest.raises(ValidationError, match="PERSONAL_AI_ENABLED cannot be true"):
        _settings(personal_ai_enabled=True)


def test_federation_export_gate_requires_identity_gate_and_defaults_off() -> None:
    assert Settings(_env_file=None, app_env="test").personal_ai_federation_export_enabled is False
    with pytest.raises(ValidationError, match="personal_ai_federation_requires_context_identity"):
        Settings(
            _env_file=None,
            app_env="test",
            personal_ai_federation_export_enabled=True,
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
        (_service_claims(email="unexpected@example.iam.gserviceaccount.com"), user_verifier.identity),
        (_service_claims(), VerifiedIdentity("https://accounts.google.com", "google-subject", issued_at=int(time.time()))),
        (_service_claims(), VerifiedIdentity(FIREBASE_ISSUER, "firebase-subject", issued_at=int(time.time()) - 601)),
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
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
    app.state.settings = _settings(personal_ai_federation_export_enabled=True)
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/v1/integrations/personal-ai/federation-export",
            headers={
                "Authorization": "Bearer service-token",
                "X-User-ID-Token": "invalid-or-unmapped-user-token",
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


def test_request_cannot_use_a_profile_item_reference_for_another_object_type() -> None:
    with pytest.raises(ValidationError):
        HealthContextReadRequest(
            operation="profile",
            category="profile_background",
            entity_refs=(("event", uuid4()),),
            fields=("record",),
        )


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
