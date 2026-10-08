from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from health_api.api.ai import router as ai_router
from health_api.api.daily import router as daily_router
from health_api.api.dependencies import get_current_owner
from health_api.api.profile import router as profile_router
from health_api.config.settings import Settings
from health_api.integrations.firebase_auth import (
    TokenVerificationError,
    VerifierUnavailable,
)
from health_api.main import create_app


class FixedVerifier:
    def __init__(self, failure: Exception) -> None:
        self.failure = failure

    def verify(self, _token: str) -> object:
        raise self.failure


def _app(verifier: FixedVerifier) -> TestClient:
    settings = Settings(
        _env_file=None,
        app_env="test",
        auth_mode="firebase",
        firebase_project_id="health-test-1234",
        database_url="postgresql+psycopg://health:health@127.0.0.1:1/health_test",
    )
    return TestClient(create_app(settings, identity_verifier=verifier))


def test_every_profile_daily_ai_and_history_route_rejects_invalid_bearers() -> None:
    client = _app(FixedVerifier(TokenVerificationError()))
    item_id = UUID("00000000-0000-0000-0000-000000000001")
    paths = [
        "/profile",
        f"/profile/{item_id}",
        f"/profile/{item_id}/history",
        "/events",
        f"/events/{item_id}",
        f"/events/{item_id}/history",
        "/observations",
        f"/observations/{item_id}",
        f"/observations/{item_id}/history",
        "/today",
        "/assistant/status",
    ]

    for path in paths:
        response = client.get(path, headers={"Authorization": "Bearer sensitive-token-value"})
        assert response.status_code == 401, path
        assert response.json()["code"] == "invalid_token"
        assert "sensitive-token-value" not in response.text

    message = client.post(
        "/assistant/messages",
        headers={"Authorization": "Bearer sensitive-token-value"},
        json={
            "message": "Review sleep",
            "scope": {"task": "Review sleep", "resource_types": ["event"]},
        },
    )
    assert message.status_code == 401
    assert message.json()["code"] == "invalid_token"
    assert "sensitive-token-value" not in message.text


def test_every_registered_owner_scoped_operation_resolves_the_verified_owner() -> None:
    domain_routes = [
        route for router in (profile_router, daily_router, ai_router) for route in router.routes
    ]
    assert domain_routes
    for route in domain_routes:
        assert any(
            dependency.call is get_current_owner for dependency in route.dependant.dependencies
        ), (
            route.path,
            route.methods,
        )


def test_missing_bearer_is_rejected_without_auth_fallback() -> None:
    client = _app(FixedVerifier(TokenVerificationError()))
    response = client.get("/profile")
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"

    status = client.get("/assistant/status")
    assert status.status_code == 401
    assert status.json()["code"] == "authentication_required"

    message = client.post(
        "/assistant/messages",
        json={
            "message": "Review sleep",
            "scope": {"task": "Review sleep", "resource_types": ["event"]},
        },
    )
    assert message.status_code == 401
    assert message.json()["code"] == "authentication_required"


def test_verifier_outage_returns_sanitized_503_and_liveness_stays_dependency_free() -> None:
    client = _app(FixedVerifier(VerifierUnavailable()))
    response = client.get("/profile", headers={"Authorization": "Bearer token-value"})
    assert response.status_code == 503
    assert response.json()["code"] == "auth_unavailable"
    assert "token-value" not in response.text
    assert client.get("/healthz").status_code == 200


def test_openapi_declares_bearer_auth_for_domain_routes_but_not_liveness() -> None:
    client = _app(FixedVerifier(TokenVerificationError()))
    document = client.get("/openapi.json").json()

    assert document["components"]["securitySchemes"]["FirebaseBearer"]["scheme"] == "bearer"
    assert document["paths"]["/profile"]["get"]["security"] == [{"FirebaseBearer": []}]
    assert "security" not in document["paths"]["/healthz"]["get"]
