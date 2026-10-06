from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from health_api.config.settings import Settings
from health_api.main import create_app

OWNER_ID = UUID("00000000-0000-0000-0000-000000000303")


@pytest_asyncio.fixture
async def ai_api_client(db_session: Session, postgres_engine: Engine) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        _env_file=None,
        app_env="test",
        auth_mode="dev",
        local_principal_id=OWNER_ID,
        local_principal_timezone="America/Los_Angeles",
    )
    app = create_app(settings, engine=postgres_engine)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


def _meal_event(occurred_at: datetime) -> dict[str, object]:
    return {
        "domain": "nutrition",
        "time": {
            "precision": "instant",
            "occurred_at": occurred_at.isoformat(),
            "timezone": "America/Los_Angeles",
        },
        "ended_at": None,
        "payload": {
            "kind": "meal",
            "label": "Review-test lunch",
            "foods": ["review-test rice"],
            "energy": {"value": 100, "unit": "kcal"},
        },
        "notes": None,
    }


@pytest.mark.asyncio
async def test_context_and_search_follow_daily_permission_revisions(
    ai_api_client: AsyncClient,
) -> None:
    object_id = uuid4()
    event = _meal_event(datetime.now(UTC) - timedelta(minutes=1))
    created = await ai_api_client.post(
        "/events",
        json={"id": str(object_id), "event": event, "ai_use_allowed": True},
    )
    assert created.status_code == 201

    scope = {
        "task": "Review-test nutrition",
        "resource_types": ["event"],
        "domains": ["nutrition"],
        "timezone": "America/Los_Angeles",
        "lookback_days": 30,
    }
    preview = await ai_api_client.post("/ai/context", json=scope)
    assert preview.status_code == 200
    assert [entry["object_id"] for entry in preview.json()["entries"]] == [str(object_id)]

    results = await ai_api_client.get("/search", params={"q": "review-test rice", "types": "event"})
    assert [item["object_id"] for item in results.json()["items"]] == [str(object_id)]

    revoked = await ai_api_client.patch(
        f"/events/{object_id}",
        json={"expected_revision": 1, "event": event, "ai_use_allowed": False},
    )
    assert revoked.status_code == 200
    assert revoked.json()["revision"] == 2

    preview_after_revoke = await ai_api_client.post("/ai/context", json=scope)
    results_after_revoke = await ai_api_client.get(
        "/search", params={"q": "review-test rice", "types": "event"}
    )
    assert preview_after_revoke.json()["entries"] == []
    assert results_after_revoke.json()["items"] == []


@pytest.mark.asyncio
async def test_today_summary_keeps_symptom_severity_linked_within_included_scope(
    ai_api_client: AsyncClient,
) -> None:
    event_id, observation_id = uuid4(), uuid4()
    occurred_at = datetime.now(UTC) - timedelta(minutes=1)
    symptom = {
        "domain": "symptoms",
        "time": {
            "precision": "instant",
            "occurred_at": occurred_at.isoformat(),
            "timezone": "America/Los_Angeles",
        },
        "ended_at": None,
        "payload": {"kind": "symptom", "label": "Review-test headache"},
        "notes": None,
    }
    severity = {
        "domain": "symptoms",
        "time": {
            "precision": "instant",
            "occurred_at": occurred_at.isoformat(),
            "timezone": "America/Los_Angeles",
        },
        "interval_end": None,
        "payload": {"value": {"metric": "symptom_severity", "value": 5, "unit": "score"}},
        "notes": None,
    }
    created = await ai_api_client.post(
        "/daily-entries",
        json={
            "events": [{"id": str(event_id), "event": symptom, "ai_use_allowed": True}],
            "observations": [
                {
                    "id": str(observation_id),
                    "observation": severity,
                    "ai_use_allowed": True,
                }
            ],
            "links": [{"event_id": str(event_id), "observation_id": str(observation_id)}],
        },
    )
    assert created.status_code == 201

    observations_only = await ai_api_client.post(
        "/ai/context",
        json={"task": "Review symptom severity", "resource_types": ["observation"]},
    )
    assert observations_only.status_code == 200
    assert not any(
        row["metric"] == "symptom_severity" for row in observations_only.json()["today_summaries"]
    )

    linked_scope = await ai_api_client.post(
        "/ai/context",
        json={"task": "Review symptom severity", "resource_types": ["event", "observation"]},
    )
    assert linked_scope.status_code == 200
    summary = next(
        row for row in linked_scope.json()["today_summaries"] if row["metric"] == "symptom_severity"
    )
    assert summary["known_value"] == 5
    assert summary["coverage"] == {"known_count": 1, "total_count": 1}
