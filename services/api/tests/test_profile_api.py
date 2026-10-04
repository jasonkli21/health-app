from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from health_api.config.settings import Settings
from health_api.main import create_app

OWNER_ID = UUID("00000000-0000-0000-0000-000000000101")
OTHER_OWNER_ID = UUID("00000000-0000-0000-0000-000000000202")


def settings(principal_id: UUID | None = OWNER_ID) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        auth_mode="dev",
        local_principal_id=principal_id,
        local_principal_timezone="America/Los_Angeles",
    )


@pytest_asyncio.fixture
async def api_client(db_session: Session, postgres_engine: Engine) -> AsyncIterator[AsyncClient]:
    app = create_app(settings(), engine=postgres_engine)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


def request_body(item_id: UUID | None = None) -> dict[str, object]:
    return {
        "id": str(item_id or uuid4()),
        "profile": {
            "kind": "fact",
            "category": "background",
            "key": "has_allergy",
            "label": "Has a food allergy",
            "value": {"type": "boolean", "value": False},
        },
        "valid_from": None,
        "valid_to": None,
        "ai_use_allowed": False,
        "cross_domain_use_allowed": False,
        "notes": None,
        "metadata": {},
    }


@pytest.mark.asyncio
async def test_healthcheck_is_public_and_missing_principal_fails_closed(
    postgres_engine: Engine,
) -> None:
    app = create_app(settings(None), engine=postgres_engine)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        health = await client.get("/healthz")
        assert health.status_code == 200
        response = await client.get("/profile")

    assert response.status_code == 401
    assert response.json()["code"] == "principal_unavailable"
    assert response.headers["x-request-id"] == response.json()["request_id"]


@pytest.mark.asyncio
async def test_create_retry_after_update_preserves_current_revision(
    api_client: AsyncClient,
) -> None:
    body = request_body()
    created = await api_client.post("/profile", json=body)
    assert created.status_code == 201
    first = created.json()
    assert first["revision"] == 1
    assert first["profile"]["value"] == {"type": "boolean", "value": False}
    assert first["permissions"] == {
        "ai_use_allowed": False,
        "cross_domain_use_allowed": False,
    }
    assert first["source"]["kind"] == "manual"
    assert first["confirmation_status"] == "user_confirmed"

    updated = await api_client.patch(
        f"/profile/{body['id']}",
        json={
            "expected_revision": 1,
            "profile": {
                "kind": "fact",
                "category": "background",
                "key": "has_allergy",
                "label": "Allergy status",
                "value": {"type": "boolean", "value": True},
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2

    retried = await api_client.post("/profile", json=body)
    assert retried.status_code == 200
    assert retried.json()["revision"] == 2
    assert retried.json()["profile"]["label"] == "Allergy status"


@pytest.mark.asyncio
async def test_patch_distinguishes_omission_from_null_clearing(api_client: AsyncClient) -> None:
    body = request_body()
    body["notes"] = "temporary note"
    body["valid_from"] = "2020-01-01T00:00:00Z"
    body["metadata"] = {"display_hint": "private"}
    created = await api_client.post("/profile", json=body)
    item_id = body["id"]

    changed = await api_client.patch(
        f"/profile/{item_id}",
        json={"expected_revision": 1, "notes": None, "valid_from": None, "metadata": None},
    )
    assert created.status_code == 201
    assert changed.status_code == 200
    data = changed.json()
    assert data["notes"] is None
    assert data["valid_from"] is None
    assert data["metadata"] == {}
    assert data["profile"]["value"]["value"] is False

    invalid = await api_client.patch(
        f"/profile/{item_id}", json={"expected_revision": 2, "profile": None}
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_stale_revision_is_conflict_and_foreign_owner_is_not_found(
    api_client: AsyncClient, postgres_engine: Engine
) -> None:
    created = await api_client.post("/profile", json=request_body())
    item_id = created.json()["id"]
    stale = await api_client.patch(
        f"/profile/{item_id}", json={"expected_revision": 4, "notes": "stale"}
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "conflict"
    unknown = await api_client.get(f"/profile/{uuid4()}")
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "not_found"

    other_app = create_app(settings(OTHER_OWNER_ID), engine=postgres_engine)
    async with AsyncClient(
        transport=ASGITransport(app=other_app), base_url="http://testserver"
    ) as other_client:
        foreign = await other_client.get(
            f"/profile/{item_id}", headers={"X-User-ID": str(OWNER_ID)}
        )
    assert foreign.status_code == 404
    assert foreign.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_reused_create_id_with_different_content_is_conflict(api_client: AsyncClient) -> None:
    body = request_body()
    created = await api_client.post("/profile", json=body)
    assert created.status_code == 201

    profile_body = body["profile"]
    assert isinstance(profile_body, dict)
    body["profile"] = {**profile_body, "label": "Changed content"}
    conflict = await api_client.post("/profile", json=body)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_database_unavailable_returns_sanitized_503() -> None:
    broken_settings = Settings(
        _env_file=None,
        app_env="test",
        auth_mode="dev",
        local_principal_id=OWNER_ID,
        database_url="postgresql+psycopg://health@127.0.0.1:1/health_phase1?connect_timeout=1",
    )
    app = create_app(broken_settings)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/profile")
    app.state.engine.dispose()

    assert response.status_code == 503
    assert response.json()["code"] == "service_unavailable"
    assert "psycopg" not in response.text
    assert "127.0.0.1" not in response.text


@pytest.mark.asyncio
async def test_list_pagination_is_stable_and_bound_to_owner_and_filter(
    api_client: AsyncClient, postgres_engine: Engine
) -> None:
    await api_client.post("/profile", json=request_body())
    await api_client.post("/profile", json=request_body())
    first_page = await api_client.get("/profile", params={"limit": 1})
    assert first_page.status_code == 200
    first_data = first_page.json()
    assert len(first_data["items"]) == 1
    cursor = first_data["next_cursor"]
    assert cursor

    second_page = await api_client.get(
        "/profile",
        params={"limit": 1, "cursor": cursor, "as_of": first_data["as_of"]},
    )
    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 1
    assert second_page.json()["items"][0]["id"] != first_data["items"][0]["id"]

    bad_filter = await api_client.get(
        "/profile",
        params={
            "limit": 1,
            "cursor": cursor,
            "as_of": first_data["as_of"],
            "category": "preferences",
        },
    )
    assert bad_filter.status_code == 422
    assert bad_filter.json()["code"] == "invalid_cursor"

    other_app = create_app(settings(OTHER_OWNER_ID), engine=postgres_engine)
    async with AsyncClient(
        transport=ASGITransport(app=other_app), base_url="http://testserver"
    ) as other_client:
        bad_owner = await other_client.get(
            "/profile",
            params={"limit": 1, "cursor": cursor, "as_of": first_data["as_of"]},
        )
    assert bad_owner.status_code == 422
    assert bad_owner.json()["code"] == "invalid_cursor"


@pytest.mark.asyncio
async def test_history_archive_and_active_list_semantics(api_client: AsyncClient) -> None:
    created = await api_client.post("/profile", json=request_body())
    item_id = created.json()["id"]
    await api_client.patch(f"/profile/{item_id}", json={"expected_revision": 1, "notes": "Changed"})
    history = await api_client.get(f"/profile/{item_id}/history", params={"limit": 1})
    assert history.status_code == 200
    assert len(history.json()["items"]) == 1
    assert history.json()["next_after_revision"] == 1
    next_history = await api_client.get(
        f"/profile/{item_id}/history",
        params={"after_revision": history.json()["next_after_revision"]},
    )
    assert [row["revision"] for row in next_history.json()["items"]] == [2]

    archived = await api_client.delete(f"/profile/{item_id}", params={"expected_revision": 2})
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    active_list = await api_client.get("/profile")
    assert all(row["id"] != item_id for row in active_list.json()["items"])
    detail = await api_client.get(f"/profile/{item_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_validation_errors_and_body_limit_never_echo_values(api_client: AsyncClient) -> None:
    marker = "SECRET-SUBMITTED-HEALTH-TEXT"
    invalid = request_body()
    invalid["profile"] = {
        "kind": "fact",
        "category": "background",
        "key": "health_note",
        "label": "A note",
        "value": {"type": "text", "value": marker},
        marker: marker,
    }
    response = await api_client.post("/profile", json=invalid)
    assert response.status_code == 422
    assert marker not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"]

    oversized = await api_client.post(
        "/profile", content=b" " * 65_537, headers={"content-type": "application/json"}
    )
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "request_too_large"


@pytest.mark.asyncio
async def test_openapi_has_stable_transport_paths_and_no_server_secrets(
    postgres_engine: Engine,
) -> None:
    app: FastAPI = create_app(settings(), engine=postgres_engine)
    document = app.openapi()
    operations = {
        document["paths"][path][method]["operationId"]
        for path, methods in document["paths"].items()
        for method in methods
    }
    assert {
        "listProfileItems",
        "createProfileItem",
        "getProfileItem",
        "listProfileHistory",
        "updateProfileItem",
        "archiveProfileItem",
        "healthcheck",
    } <= operations
    serialized = str(document)
    assert "database_url" not in serialized
    assert "postgresql+psycopg" not in serialized
    assert "00000000-0000-0000-0000-000000000101" not in serialized
    assert set(document["paths"]["/profile"]["post"]["responses"]) >= {"200", "201", "409"}
    patch_schema = document["components"]["schemas"]["ProfilePatchRequest"]["properties"]
    for field in ("profile", "ai_use_allowed", "cross_domain_use_allowed"):
        property_schema = patch_schema[field]
        variants = property_schema.get("anyOf", [property_schema])
        assert all(variant.get("type") != "null" for variant in variants)
    assert "explicit null is invalid" in patch_schema["profile"]["description"]
    assert "65,536 bytes" in document["info"]["description"]
