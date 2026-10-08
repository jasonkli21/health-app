from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from health_api.api.dependencies import get_current_owner
from health_api.config.settings import Settings
from health_api.domain.ai import AIContextPack
from health_api.main import create_app
from sqlalchemy import create_engine

OWNER_ID = UUID("00000000-0000-0000-0000-000000000304")


@pytest.fixture
def ai_boundary_app() -> Generator[FastAPI, None, None]:
    engine = create_engine("sqlite://")
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            auth_mode="dev",
            local_principal_id=OWNER_ID,
        ),
        engine=engine,
    )
    app.dependency_overrides[get_current_owner] = lambda: OWNER_ID
    yield app
    engine.dispose()


@pytest.fixture
def ai_boundary_client(ai_boundary_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(ai_boundary_app) as client:
        yield client


def test_assistant_status_is_disabled_with_no_live_capabilities(
    ai_boundary_client: TestClient,
) -> None:
    response = ai_boundary_client.get("/assistant/status")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "adapter_status": "disabled",
        "allowed_capabilities": [],
        "message": (
            "Live Assistant messaging is unavailable until the Personal AI Application "
            "Integration Contract is implemented and reviewed."
        ),
    }


def test_assistant_message_cannot_build_context_or_call_an_adapter(
    ai_boundary_app: FastAPI,
    ai_boundary_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SpyAdapter:
        calls = 0

        async def send_message(self, *_args: object, **_kwargs: object) -> None:
            self.calls += 1

    adapter = SpyAdapter()
    ai_boundary_app.state.personal_ai_status = adapter

    def fail_if_context_is_built(*_args: object, **_kwargs: object) -> None:
        pytest.fail("disabled Assistant messaging must not build Health context")

    monkeypatch.setattr("health_api.api.ai.build_ai_context", fail_if_context_is_built)
    response = ai_boundary_client.post(
        "/assistant/messages",
        json={
            "message": "Review my recent sleep.",
            "scope": {"task": "Review sleep", "resource_types": ["event"]},
        },
    )

    assert response.status_code == 503
    assert response.json()["code"] == "assistant_unavailable"
    assert response.json()["message"] == (
        "Live Assistant messaging is unavailable until the Personal AI Application "
        "Integration Contract is implemented and reviewed."
    )
    assert adapter.calls == 0


def test_local_context_preview_and_search_do_not_require_personal_ai(
    ai_boundary_app: FastAPI,
    ai_boundary_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built_at = datetime(2026, 10, 8, 12, tzinfo=UTC)
    preview = AIContextPack(
        schema_version=1,
        request_id=UUID("00000000-0000-0000-0000-000000000305"),
        owner_scope="0" * 64,
        built_at=built_at,
        as_of=built_at,
        timezone="America/Los_Angeles",
        task="Review sleep",
        task_kind="general_wellness",
        resource_types=["event"],
        domains=[],
        sections=["entries"],
        lookback_days=30,
        entries=[],
        today_summary_date=date(2026, 10, 8),
        today_summary_scope="included_opted_in_entries_only",
        today_summaries=[],
        included_counts={},
        omitted_by_user=0,
        omitted_by_budget=0,
        truncated=False,
        budget_bytes=65536,
        serialized_bytes=0,
    )

    monkeypatch.setattr("health_api.api.ai.build_ai_context", lambda *_args: preview)
    monkeypatch.setattr(
        "health_api.api.ai.owner_today_settings",
        lambda *_args: (date(2026, 10, 8), "America/Los_Angeles"),
    )
    monkeypatch.setattr(
        "health_api.api.ai.search_ai_resources", lambda *_args, **_kwargs: ([], None)
    )

    context_response = ai_boundary_client.post(
        "/ai/context",
        json={"task": "Review sleep", "resource_types": ["event"]},
    )
    search_response = ai_boundary_client.get("/search", params={"q": "sleep"})

    assert ai_boundary_app.state.personal_ai_status.configured is False
    assert context_response.status_code == 200
    assert context_response.json()["task"] == "Review sleep"
    assert search_response.status_code == 200
    assert search_response.json() == {"items": [], "next_cursor": None}
