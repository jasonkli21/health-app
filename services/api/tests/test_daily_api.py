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

OWNER_ID = UUID("00000000-0000-0000-0000-000000000111")
OTHER_OWNER_ID = UUID("00000000-0000-0000-0000-000000000222")


def settings(principal_id: UUID = OWNER_ID) -> Settings:
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


def meal_event(
    local_time: str,
    *,
    energy: float | None = 100,
    local_date: str = "2026-05-01",
) -> dict[str, object]:
    time_value: dict[str, object]
    if local_time == "date_only":
        time_value = {
            "precision": "date_only",
            "local_date": local_date,
            "timezone": "America/Los_Angeles",
        }
    else:
        time_value = {
            "precision": "instant",
            "occurred_at": local_time,
            "timezone": "America/Los_Angeles",
        }
    return {
        "domain": "nutrition",
        "time": time_value,
        "ended_at": None,
        "payload": {
            "kind": "meal",
            "label": "Lunch",
            "foods": ["rice"],
            "energy": {"value": energy, "unit": "kcal"} if energy is not None else None,
        },
        "notes": None,
    }


def event_request(event: dict[str, object], item_id: UUID | None = None) -> dict[str, object]:
    return {"id": str(item_id or uuid4()), "event": event}


def observation(
    metric: str,
    value: float,
    unit: str,
    occurred_at: str = "2026-05-01T16:00:00Z",
    *,
    domain: str = "measurements",
) -> dict[str, object]:
    return {
        "domain": domain,
        "time": {
            "precision": "instant",
            "occurred_at": occurred_at,
            "timezone": "America/Los_Angeles",
        },
        "interval_end": None,
        "payload": {"value": {"metric": metric, "value": value, "unit": unit}},
        "notes": None,
    }


@pytest.mark.asyncio
async def test_event_create_idempotency_history_archive_and_date_range(
    api_client: AsyncClient,
) -> None:
    body = event_request(meal_event("2026-05-01T17:00:00Z"))
    created = await api_client.post("/events", json=body)
    assert created.status_code == 201
    item = created.json()
    assert item["object_type"] == "event"
    assert item["source"]["kind"] == "manual"
    assert item["confirmation_status"] == "user_confirmed"
    assert item["permissions"] == {"ai_use_allowed": False, "cross_domain_use_allowed": False}
    assert item["event"]["time"]["occurred_at"] == "2026-05-01T17:00:00Z"

    retry = await api_client.post("/events", json=body)
    assert retry.status_code == 200
    assert retry.json()["revision"] == 1

    updated = await api_client.patch(
        f"/events/{body['id']}",
        json={"expected_revision": 1, "event": meal_event("2026-05-01T17:00:00Z", energy=125)},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    stale = await api_client.patch(
        f"/events/{body['id']}",
        json={"expected_revision": 1, "event": meal_event("2026-05-01T17:00:00Z", energy=150)},
    )
    assert stale.status_code == 409
    history = await api_client.get(f"/events/{body['id']}/history")
    assert [entry["reason"] for entry in history.json()["items"]] == ["create", "update"]
    assert history.json()["items"][0]["snapshot"]["event"]["payload"]["energy"]["value"] == 100

    listed = await api_client.get(
        "/events", params={"from_date": "2026-05-01", "to_date": "2026-05-01"}
    )
    assert [entry["id"] for entry in listed.json()["items"]] == [body["id"]]
    archived = await api_client.delete(f"/events/{body['id']}", params={"expected_revision": 2})
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    after_archive = await api_client.get("/events")
    assert after_archive.json()["items"] == []


@pytest.mark.asyncio
async def test_compound_symptom_entry_and_blood_pressure_are_atomic_and_roll_up_once(
    api_client: AsyncClient,
) -> None:
    symptom_id, severity_id = uuid4(), uuid4()
    symptom = {
        "domain": "symptoms",
        "time": {
            "precision": "instant",
            "occurred_at": "2026-05-01T16:00:00Z",
            "timezone": "America/Los_Angeles",
        },
        "ended_at": None,
        "payload": {"kind": "symptom", "label": "Headache"},
        "notes": None,
    }
    severity = observation(
        "symptom_severity", 5, "score", domain="symptoms", occurred_at="2026-05-01T16:00:00Z"
    )
    compound = await api_client.post(
        "/daily-entries",
        json={
            "events": [{"id": str(symptom_id), "event": symptom, "ai_use_allowed": True}],
            "observations": [
                {"id": str(severity_id), "observation": severity, "ai_use_allowed": False}
            ],
            "links": [{"event_id": str(symptom_id), "observation_id": str(severity_id)}],
        },
    )
    assert compound.status_code == 201
    assert compound.json()["events"][0]["linked_observation_ids"] == [str(severity_id)]
    assert compound.json()["events"][0]["permissions"]["ai_use_allowed"] is True
    assert compound.json()["observations"][0]["permissions"]["ai_use_allowed"] is False
    assert compound.json()["observations"][0]["revision"] == 1
    today_after_compound = await api_client.get("/today", params={"date": "2026-05-01"})
    assert today_after_compound.json()["as_of_sequence"] == 1
    assert {item["id"] for item in today_after_compound.json()["items"]} == {
        str(symptom_id),
        str(severity_id),
    }

    unlinked = await api_client.post(
        "/observations",
        json={"id": str(uuid4()), "observation": severity},
    )
    assert unlinked.status_code == 422
    assert unlinked.json()["code"] == "validation_error"

    pressure_time = "2026-05-01T18:00:00Z"
    pressure = await api_client.post(
        "/daily-entries",
        json={
            "events": [],
            "observations": [
                {
                    "id": str(uuid4()),
                    "observation": observation("systolic_pressure", 120, "mmHg", pressure_time),
                },
                {
                    "id": str(uuid4()),
                    "observation": observation("diastolic_pressure", 80, "mmHg", pressure_time),
                },
            ],
            "links": [],
        },
    )
    assert pressure.status_code == 201
    today = await api_client.get("/today", params={"date": "2026-05-01"})
    summaries = {(row["domain"], row["metric"]): row for row in today.json()["summaries"]}
    assert summaries[("symptoms", "symptom_episode_count")]["known_value"] == 1
    assert summaries[("symptoms", "symptom_severity")]["known_value"] == 5
    assert summaries[("symptoms", "symptom_severity")]["logged_count"] == 1
    assert summaries[("measurements", "systolic_pressure")]["known_value"] == 120
    assert summaries[("measurements", "diastolic_pressure")]["known_value"] == 80


@pytest.mark.asyncio
async def test_wrong_resource_delete_returns_404_without_archiving_or_allocating_sequence(
    api_client: AsyncClient,
) -> None:
    event = await api_client.post("/events", json=event_request(meal_event("2026-05-01T17:00:00Z")))
    observation_id = uuid4()
    observation_result = await api_client.post(
        "/observations",
        json={
            "id": str(observation_id),
            "observation": observation("weight", 70, "kg"),
        },
    )
    assert event.status_code == observation_result.status_code == 201
    event_id = UUID(event.json()["id"])
    before = await api_client.get("/today", params={"date": "2026-05-01"})

    wrong_event_delete = await api_client.delete(
        f"/events/{observation_id}", params={"expected_revision": 1}
    )
    wrong_observation_delete = await api_client.delete(
        f"/observations/{event_id}", params={"expected_revision": 1}
    )
    assert wrong_event_delete.status_code == wrong_observation_delete.status_code == 404

    event_after = await api_client.get(f"/events/{event_id}")
    observation_after = await api_client.get(f"/observations/{observation_id}")
    event_history = await api_client.get(f"/events/{event_id}/history")
    observation_history = await api_client.get(f"/observations/{observation_id}/history")
    after = await api_client.get("/today", params={"date": "2026-05-01"})
    assert event_after.json()["status"] == observation_after.json()["status"] == "active"
    assert event_after.json()["revision"] == observation_after.json()["revision"] == 1
    assert len(event_history.json()["items"]) == len(observation_history.json()["items"]) == 1
    assert after.json()["as_of_sequence"] == before.json()["as_of_sequence"]


@pytest.mark.asyncio
async def test_sleep_with_only_a_known_date_or_start_has_partial_unknown_duration(
    api_client: AsyncClient,
) -> None:
    sleep_ids = [uuid4(), uuid4()]
    date_only_sleep = {
        "domain": "sleep",
        "time": {
            "precision": "date_only",
            "local_date": "2026-05-01",
            "timezone": "America/Los_Angeles",
        },
        "ended_at": None,
        "payload": {"kind": "sleep", "quality": None},
        "notes": None,
    }
    started_sleep = {
        **date_only_sleep,
        "time": {
            "precision": "instant",
            "occurred_at": "2026-05-01T23:00:00-07:00",
            "timezone": "America/Los_Angeles",
        },
    }
    for object_id, entry in zip(sleep_ids, (date_only_sleep, started_sleep), strict=True):
        response = await api_client.post("/events", json={"id": str(object_id), "event": entry})
        assert response.status_code == 201

    today = await api_client.get("/today", params={"date": "2026-05-01"})
    duration = next(
        summary
        for summary in today.json()["summaries"]
        if summary["domain"] == "sleep" and summary["metric"] == "duration"
    )
    assert duration["known_value"] is None
    assert duration["logged_count"] == 2
    assert duration["coverage"] == {"known_count": 0, "total_count": 2}
    assert duration["partial"] is True


@pytest.mark.asyncio
async def test_conversion_bound_is_a_sanitized_input_error_before_persistence(
    api_client: AsyncClient,
) -> None:
    before = await api_client.get("/today", params={"date": "2026-05-01"})
    rejected = await api_client.post(
        "/events",
        json={
            "id": str(uuid4()),
            "event": {
                "domain": "exercise",
                "time": {
                    "precision": "date_only",
                    "local_date": "2026-05-01",
                    "timezone": "America/Los_Angeles",
                },
                "ended_at": None,
                "payload": {
                    "kind": "workout",
                    "label": "Walk",
                    "distance": {"value": 1e300, "unit": "mi"},
                },
                "notes": None,
            },
        },
    )
    after = await api_client.get("/today", params={"date": "2026-05-01"})
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "validation_error"
    assert any(field["field"].endswith("distance") for field in rejected.json()["field_errors"])
    assert "1e+300" not in rejected.text
    assert after.json()["as_of_sequence"] == before.json()["as_of_sequence"]


@pytest.mark.asyncio
async def test_symptom_severity_coverage_includes_unrated_episodes_and_excludes_archived_links(
    api_client: AsyncClient,
) -> None:
    rated_id, unrated_id, severity_id = uuid4(), uuid4(), uuid4()
    symptom = {
        "domain": "symptoms",
        "time": {
            "precision": "instant",
            "occurred_at": "2026-05-01T16:00:00Z",
            "timezone": "America/Los_Angeles",
        },
        "ended_at": None,
        "payload": {"kind": "symptom", "label": "Headache"},
        "notes": None,
    }
    severity = observation(
        "symptom_severity", 5, "score", domain="symptoms", occurred_at="2026-05-01T16:00:00Z"
    )
    created = await api_client.post(
        "/daily-entries",
        json={
            "events": [
                {"id": str(rated_id), "event": symptom},
                {
                    "id": str(unrated_id),
                    "event": {**symptom, "payload": {"kind": "symptom", "label": "Nausea"}},
                },
            ],
            "observations": [{"id": str(severity_id), "observation": severity}],
            "links": [{"event_id": str(rated_id), "observation_id": str(severity_id)}],
        },
    )
    assert created.status_code == 201

    def severity_summary(response: object) -> dict[str, object]:
        payload = response.json()  # type: ignore[attr-defined]
        return next(
            row
            for row in payload["summaries"]
            if row["domain"] == "symptoms" and row["metric"] == "symptom_severity"
        )

    today = await api_client.get("/today", params={"date": "2026-05-01"})
    initial = severity_summary(today)
    assert initial["known_value"] == 5
    assert initial["logged_count"] == 2
    assert initial["coverage"] == {"known_count": 1, "total_count": 2}
    assert initial["partial"] is True

    archived_observation = await api_client.delete(
        f"/observations/{severity_id}", params={"expected_revision": 1}
    )
    assert archived_observation.status_code == 200
    after_observation_archive = severity_summary(
        await api_client.get("/today", params={"date": "2026-05-01"})
    )
    assert after_observation_archive["known_value"] is None
    assert after_observation_archive["coverage"] == {"known_count": 0, "total_count": 2}
    assert after_observation_archive["partial"] is True

    archived_event = await api_client.delete(f"/events/{rated_id}", params={"expected_revision": 1})
    assert archived_event.status_code == 200
    after_event_archive = severity_summary(
        await api_client.get("/today", params={"date": "2026-05-01"})
    )
    assert after_event_archive["logged_count"] == 1
    assert after_event_archive["coverage"] == {"known_count": 0, "total_count": 1}


@pytest.mark.asyncio
async def test_active_severity_linked_to_archived_episode_is_not_counted_as_unlinked(
    api_client: AsyncClient,
) -> None:
    event_id, severity_id = uuid4(), uuid4()
    symptom = {
        "domain": "symptoms",
        "time": {
            "precision": "instant",
            "occurred_at": "2026-05-01T16:00:00Z",
            "timezone": "America/Los_Angeles",
        },
        "ended_at": None,
        "payload": {"kind": "symptom", "label": "Headache"},
        "notes": None,
    }
    severity = observation(
        "symptom_severity", 4, "score", domain="symptoms", occurred_at="2026-05-01T16:00:00Z"
    )
    created = await api_client.post(
        "/daily-entries",
        json={
            "events": [{"id": str(event_id), "event": symptom}],
            "observations": [{"id": str(severity_id), "observation": severity}],
            "links": [{"event_id": str(event_id), "observation_id": str(severity_id)}],
        },
    )
    assert created.status_code == 201
    archived = await api_client.delete(f"/events/{event_id}", params={"expected_revision": 1})
    assert archived.status_code == 200
    active_severity = await api_client.get(f"/observations/{severity_id}")
    assert active_severity.status_code == 200
    assert active_severity.json()["status"] == "active"

    today = await api_client.get("/today", params={"date": "2026-05-01"})
    severity_summary = next(
        row
        for row in today.json()["summaries"]
        if row["domain"] == "symptoms" and row["metric"] == "symptom_severity"
    )
    assert severity_summary["known_value"] is None
    assert severity_summary["logged_count"] == 0
    assert severity_summary["coverage"] == {"known_count": 0, "total_count": 0}


@pytest.mark.asyncio
async def test_today_continuation_uses_fixed_revision_snapshot_after_mutations(
    api_client: AsyncClient,
) -> None:
    first_body = event_request(meal_event("2026-05-01T17:00:00Z", energy=100))
    second_body = event_request(meal_event("2026-05-01T16:00:00Z", energy=50))
    assert (await api_client.post("/events", json=first_body)).status_code == 201
    assert (await api_client.post("/events", json=second_body)).status_code == 201

    first_page = await api_client.get("/today", params={"date": "2026-05-01", "limit": 1})
    assert first_page.status_code == 200
    first = first_page.json()
    assert first["items"][0]["id"] == first_body["id"]
    assert first["as_of_sequence"] > 0
    assert first["next_cursor"]
    assert first["includes_profile_context"] is True
    assert first["summaries"][0]["known_value"] == 150

    changed = await api_client.patch(
        f"/events/{first_body['id']}",
        json={"expected_revision": 1, "event": meal_event("2026-05-01T19:00:00Z", energy=300)},
    )
    archived = await api_client.delete(
        f"/events/{second_body['id']}", params={"expected_revision": 1}
    )
    later_body = event_request(meal_event("2026-05-01T18:00:00Z", energy=900))
    later = await api_client.post("/events", json=later_body)
    assert changed.status_code == archived.status_code == later.status_code == 200 or (
        changed.status_code == 200 and archived.status_code == 200 and later.status_code == 201
    )

    continuation = await api_client.get(
        "/today",
        params={"date": "2026-05-01", "limit": 1, "cursor": first["next_cursor"]},
    )
    assert continuation.status_code == 200
    page = continuation.json()
    assert [entry["id"] for entry in page["items"]] == [second_body["id"]]
    assert page["items"][0]["status"] == "active"
    assert page["summaries"][0]["known_value"] == 150
    assert page["includes_profile_context"] is False
    assert page["profile_context_refs"] == []


@pytest.mark.asyncio
async def test_date_only_entries_keep_calendar_precision_and_cursor_binds_filters(
    api_client: AsyncClient,
) -> None:
    body = event_request(meal_event("date_only", local_date="2026-05-01"))
    created = await api_client.post("/events", json=body)
    assert created.status_code == 201
    second = await api_client.post(
        "/events", json=event_request(meal_event("date_only", energy=0, local_date="2026-05-01"))
    )
    assert second.status_code == 201
    assert created.json()["event"]["time"] == {
        "precision": "date_only",
        "local_date": "2026-05-01",
        "timezone": "America/Los_Angeles",
    }
    today = await api_client.get("/today", params={"date": "2026-05-01", "limit": 1})
    assert today.status_code == 200
    assert today.json()["items"][0]["event"]["time"]["precision"] == "date_only"
    cursor = today.json()["next_cursor"]
    if cursor:
        invalid = await api_client.get(
            "/today",
            params={"date": "2026-05-02", "cursor": cursor},
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "invalid_cursor"

    invalid_range = await api_client.get(
        "/events", params={"from_date": "2026-01-01", "to_date": "2027-01-02"}
    )
    assert invalid_range.status_code == 422
    assert invalid_range.json()["code"] == "invalid_time_range"


@pytest.mark.asyncio
async def test_resource_cursor_is_stable_and_bound_to_its_filters(api_client: AsyncClient) -> None:
    for hour in (16, 17, 18):
        body = event_request(meal_event(f"2026-05-01T{hour}:00:00Z"))
        response = await api_client.post("/events", json=body)
        assert response.status_code == 201

    first = await api_client.get("/events", params={"limit": 1, "timezone": "America/Los_Angeles"})
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["next_cursor"]
    next_page = await api_client.get(
        "/events",
        params={
            "limit": 1,
            "timezone": "America/Los_Angeles",
            "cursor": first_data["next_cursor"],
        },
    )
    assert next_page.status_code == 200
    assert next_page.json()["items"][0]["id"] != first_data["items"][0]["id"]

    mismatched_filter = await api_client.get(
        "/events",
        params={
            "limit": 1,
            "timezone": "America/New_York",
            "cursor": first_data["next_cursor"],
        },
    )
    assert mismatched_filter.status_code == 422
    assert mismatched_filter.json()["code"] == "invalid_cursor"


@pytest.mark.asyncio
async def test_today_rejects_a_snapshot_over_the_bounded_candidate_limit(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from health_api.application import today_service

    monkeypatch.setattr(today_service, "MAX_TODAY_OBJECTS", 1)
    for hour in (16, 17):
        response = await api_client.post(
            "/events", json=event_request(meal_event(f"2026-05-01T{hour}:00:00Z"))
        )
        assert response.status_code == 201

    oversized = await api_client.get("/today", params={"date": "2026-05-01"})
    assert oversized.status_code == 422
    assert oversized.json()["code"] == "today_window_too_large"
    assert "payload" not in oversized.text


@pytest.mark.asyncio
async def test_daily_reads_are_owner_scoped_and_body_errors_are_sanitized(
    api_client: AsyncClient, postgres_engine: Engine
) -> None:
    body = event_request(meal_event("2026-05-01T17:00:00Z"))
    created = await api_client.post("/events", json=body)
    assert created.status_code == 201

    other_app: FastAPI = create_app(settings(OTHER_OWNER_ID), engine=postgres_engine)
    async with AsyncClient(
        transport=ASGITransport(app=other_app), base_url="http://testserver"
    ) as client:
        get_item = await client.get(f"/events/{body['id']}")
        history = await client.get(f"/events/{body['id']}/history")
    assert get_item.status_code == history.status_code == 404
    assert get_item.json()["code"] == history.json()["code"] == "not_found"

    malformed = await api_client.post(
        "/events",
        json={"id": str(uuid4()), "event": {"private_token": "do-not-echo"}},
    )
    assert malformed.status_code == 422
    assert malformed.json()["code"] == "validation_error"
    assert "do-not-echo" not in malformed.text
