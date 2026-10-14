from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from threading import Event
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import health_api.api.daily as daily_api
from health_api.config.settings import Settings
from health_api.main import create_app

OWNER_ID = UUID("00000000-0000-0000-0000-000000000811")


def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        auth_mode="dev",
        local_principal_id=OWNER_ID,
        local_principal_timezone="America/Los_Angeles",
    )


@pytest_asyncio.fixture
async def api_client(db_session: Session, postgres_engine: Engine) -> AsyncIterator[AsyncClient]:
    app: FastAPI = create_app(settings(), engine=postgres_engine)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


def workout_record(duration: float = 30) -> dict[str, object]:
    return {
        "domain": "exercise",
        "time": {
            "precision": "instant",
            "occurred_at": "2026-10-01T16:00:00Z",
            "timezone": "America/Los_Angeles",
        },
        "ended_at": None,
        "payload": {
            "kind": "workout",
            "label": "Running",
            "duration": {"value": duration, "unit": "min"},
            "distance": {"value": 5000, "unit": "m"},
        },
        "notes": None,
    }


def workout_batch(
    *,
    batch_id: UUID,
    sample_id: UUID,
    installation_id: UUID,
    duration: float = 30,
    tombstones: list[str] | None = None,
) -> dict[str, object]:
    return {
        "batch_id": str(batch_id),
        "device_installation_id": str(installation_id),
        "resource_type": "workouts",
        "policy_version": "healthkit-v1",
        "entries": (
            [
                {
                    "source_sample_id": str(sample_id),
                    "record": workout_record(duration),
                    "metadata": {"source_bundle_identifier": "com.example.health"},
                }
            ]
            if tombstones is None
            else []
        ),
        "tombstones": [{"source_sample_id": item} for item in (tombstones or [])],
    }


def steps_batch(
    *,
    batch_id: UUID,
    installation_id: UUID,
    count: int,
    local_date: str = "2026-10-01",
    timezone: str = "America/Los_Angeles",
    source_revision: int = 1,
) -> dict[str, object]:
    return {
        "batch_id": str(batch_id),
        "device_installation_id": str(installation_id),
        "resource_type": "steps",
        "policy_version": "healthkit-v1",
        "entries": [
            {
                "source_sample_id": (
                    f"daily:{local_date}:{timezone}:healthkit-v1:{installation_id}"
                ),
                "record": {
                    "domain": "exercise",
                    "time": {
                        "precision": "date_only",
                        "local_date": local_date,
                        "timezone": timezone,
                    },
                    "interval_end": None,
                    "payload": {"value": {"metric": "steps", "value": count, "unit": "steps"}},
                    "notes": None,
                },
                "metadata": {
                    "aggregation_method_version": "hk-steps-source-v1",
                    "source_revision": source_revision,
                },
            }
        ],
        "tombstones": [],
    }


@pytest.mark.asyncio
async def test_healthkit_batch_replay_update_manual_correction_and_tombstone(
    api_client: AsyncClient,
) -> None:
    installation_id, sample_id = uuid4(), uuid4()
    first_batch_id = uuid4()
    request = workout_batch(
        batch_id=first_batch_id,
        sample_id=sample_id,
        installation_id=installation_id,
    )
    created = await api_client.post("/imports/healthkit/batches", json=request)
    assert created.status_code == 201
    assert created.json()["created_count"] == 1
    replay = await api_client.post("/imports/healthkit/batches", json=request)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True

    changed_batch = await api_client.post(
        "/imports/healthkit/batches",
        json=workout_batch(
            batch_id=uuid4(),
            sample_id=sample_id,
            installation_id=installation_id,
            duration=35,
        ),
    )
    assert changed_batch.status_code == 201
    assert changed_batch.json()["updated_count"] == 1

    status = await api_client.get("/imports/healthkit/status")
    assert status.status_code == 200
    assert status.json()["server_ingest_enabled"] is True
    assert status.json()["types"][0]["resource_type"] == "workouts"

    # The generated record ID is stable but private to the authenticated owner; find it
    # through the existing owner-scoped daily API rather than trusting a caller object ID.
    listed = await api_client.get("/events")
    item = listed.json()["items"][0]
    assert item["event"]["payload"]["duration"]["value"] == 35
    assert item["source"]["kind"] == "device"
    assert item["confirmation_status"] == "unconfirmed"
    assert item["permissions"]["ai_use_allowed"] is False
    assert item["metadata"]["healthkit_source_bundle_identifier"] == "com.example.health"
    item_id = UUID(item["id"])

    manually_corrected = await api_client.patch(
        f"/events/{item_id}",
        json={
            "expected_revision": item["revision"],
            "event": workout_record(40),
        },
    )
    assert manually_corrected.status_code == 200
    assert manually_corrected.json()["source"]["kind"] == "manual"
    assert manually_corrected.json()["confirmation_status"] == "user_confirmed"

    correction_replay = await api_client.post(
        "/imports/healthkit/batches",
        json=workout_batch(
            batch_id=uuid4(),
            sample_id=sample_id,
            installation_id=installation_id,
            duration=45,
        ),
    )
    assert correction_replay.status_code == 201
    assert correction_replay.json()["correction_count"] == 1
    current = await api_client.get(f"/events/{item_id}")
    assert current.json()["event"]["payload"]["duration"]["value"] == 40

    tombstone = await api_client.post(
        "/imports/healthkit/batches",
        json=workout_batch(
            batch_id=uuid4(),
            sample_id=sample_id,
            installation_id=installation_id,
            tombstones=[str(sample_id)],
        ),
    )
    assert tombstone.status_code == 201
    assert tombstone.json()["correction_count"] == 1
    assert (await api_client.get(f"/events/{item_id}")).json()["status"] == "active"


@pytest.mark.asyncio
async def test_healthkit_import_is_atomic_and_rejects_high_frequency_data(
    api_client: AsyncClient,
) -> None:
    installation_id, sample_id = uuid4(), uuid4()
    valid = workout_batch(batch_id=uuid4(), sample_id=sample_id, installation_id=installation_id)
    valid_entry = valid["entries"][0]  # type: ignore[index]
    invalid = {
        **valid,
        "batch_id": str(uuid4()),
        "entries": [
            valid_entry,
            {
                "source_sample_id": str(uuid4()),
                "record": {
                    **workout_record(),
                    "raw_heart_rate_samples": [70, 71, 72],
                },
            },
        ],
    }
    response = await api_client.post("/imports/healthkit/batches", json=invalid)
    assert response.status_code == 422
    listed = await api_client.get("/events")
    assert listed.json()["items"] == []
    receipt = await api_client.get(f"/imports/healthkit/batches/{invalid['batch_id']}")
    assert receipt.status_code == 404


@pytest.mark.asyncio
async def test_device_day_aggregates_use_the_declared_preferred_installation(
    api_client: AsyncClient,
) -> None:
    first_installation, second_installation = uuid4(), uuid4()
    first = await api_client.post(
        "/imports/healthkit/batches",
        json=steps_batch(batch_id=uuid4(), installation_id=first_installation, count=8000),
    )
    alias = await api_client.post(
        "/imports/healthkit/batches",
        json=steps_batch(
            batch_id=uuid4(),
            installation_id=first_installation,
            count=9000,
            timezone="US/Pacific",
            source_revision=2,
        ),
    )
    second = await api_client.post(
        "/imports/healthkit/batches",
        json=steps_batch(batch_id=uuid4(), installation_id=second_installation, count=12000),
    )
    assert first.status_code == 201
    assert alias.status_code == 201
    assert second.status_code == 201
    assert first.json()["created_count"] == alias.json()["created_count"] == 1
    assert second.json()["created_count"] == 1

    workout = await api_client.post("/events", json={"id": str(uuid4()), "event": workout_record()})
    assert workout.status_code == 201
    before_preference_change = await api_client.get(
        "/today",
        params={"date": "2026-10-01", "timezone": "America/Los_Angeles", "limit": 1},
    )
    stale_cursor = before_preference_change.json()["next_cursor"]
    assert stale_cursor is not None

    today = await api_client.get(
        "/today", params={"date": "2026-10-01", "timezone": "America/Los_Angeles"}
    )
    steps = next(row for row in today.json()["summaries"] if row["metric"] == "steps")
    assert steps["known_value"] == 9000

    preferred = await api_client.put(
        "/imports/healthkit/source-preferences",
        json={
            "resource_type": "steps",
            "device_installation_id": str(second_installation),
            "expected_revision": 1,
        },
    )
    assert preferred.status_code == 200
    assert preferred.json()["revision"] == 2
    stale_page = await api_client.get(
        "/today",
        params={
            "date": "2026-10-01",
            "timezone": "America/Los_Angeles",
            "cursor": stale_cursor,
        },
    )
    assert stale_page.status_code == 422
    assert stale_page.json()["code"] == "invalid_cursor"
    after_switch = await api_client.get(
        "/today", params={"date": "2026-10-01", "timezone": "America/Los_Angeles"}
    )
    selected_steps = next(
        row for row in after_switch.json()["summaries"] if row["metric"] == "steps"
    )
    assert selected_steps["known_value"] == 12000

    observations = await api_client.get(
        "/observations",
        params={"from_date": "2026-10-01", "to_date": "2026-10-01"},
    )
    aggregate = next(
        row
        for row in observations.json()["items"]
        if row["observation"]["payload"]["value"]["metric"] == "steps"
        and row["observation"]["time"]["timezone"] == "US/Pacific"
    )
    corrected = await api_client.patch(
        f"/observations/{aggregate['id']}",
        json={
            "expected_revision": aggregate["revision"],
            "observation": {
                **aggregate["observation"],
                "payload": {"value": {"metric": "steps", "value": 300, "unit": "steps"}},
            },
        },
    )
    assert corrected.status_code == 200
    corrected_today = await api_client.get(
        "/today", params={"date": "2026-10-01", "timezone": "America/Los_Angeles"}
    )
    corrected_steps = next(
        row for row in corrected_today.json()["summaries"] if row["metric"] == "steps"
    )
    assert corrected_steps["known_value"] == 300


@pytest.mark.asyncio
async def test_today_read_lock_keeps_preference_change_out_of_the_page_snapshot(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_installation, second_installation = uuid4(), uuid4()
    for installation, count in ((first_installation, 8000), (second_installation, 12000)):
        response = await api_client.post(
            "/imports/healthkit/batches",
            json=steps_batch(batch_id=uuid4(), installation_id=installation, count=count),
        )
        assert response.status_code == 201
    workout = await api_client.post("/events", json={"id": str(uuid4()), "event": workout_record()})
    assert workout.status_code == 201

    reached_snapshot = Event()
    release_snapshot = Event()
    load_snapshot = daily_api.load_today_snapshot

    def pause_before_snapshot(*args: object, **kwargs: object):
        reached_snapshot.set()
        if not release_snapshot.wait(timeout=5):
            raise TimeoutError("test did not release the Today snapshot")
        return load_snapshot(*args, **kwargs)

    monkeypatch.setattr(daily_api, "load_today_snapshot", pause_before_snapshot)
    read_task = asyncio.create_task(
        api_client.get(
            "/today",
            params={"date": "2026-10-01", "timezone": "America/Los_Angeles", "limit": 1},
        )
    )
    assert await asyncio.to_thread(reached_snapshot.wait, 5)

    preference_task = asyncio.create_task(
        api_client.put(
            "/imports/healthkit/source-preferences",
            json={
                "resource_type": "steps",
                "device_installation_id": str(second_installation),
                "expected_revision": 1,
            },
        )
    )
    await asyncio.sleep(0.1)
    assert not preference_task.done()
    release_snapshot.set()
    first_page, preference = await asyncio.gather(read_task, preference_task)
    assert first_page.status_code == preference.status_code == 200
    cursor = first_page.json()["next_cursor"]
    assert cursor is not None
    next_page = await api_client.get(
        "/today",
        params={
            "date": "2026-10-01",
            "timezone": "America/Los_Angeles",
            "cursor": cursor,
        },
    )
    assert next_page.status_code == 422
    assert next_page.json()["code"] == "invalid_cursor"


@pytest.mark.asyncio
async def test_aggregate_revisions_reject_stale_batches_and_allow_post_delete_recompute(
    api_client: AsyncClient,
) -> None:
    installation_id = uuid4()
    first = await api_client.post(
        "/imports/healthkit/batches",
        json=steps_batch(
            batch_id=uuid4(), installation_id=installation_id, count=100, source_revision=1
        ),
    )
    newest = await api_client.post(
        "/imports/healthkit/batches",
        json=steps_batch(
            batch_id=uuid4(), installation_id=installation_id, count=200, source_revision=2
        ),
    )
    stale = await api_client.post(
        "/imports/healthkit/batches",
        json=steps_batch(
            batch_id=uuid4(), installation_id=installation_id, count=50, source_revision=1
        ),
    )
    same_revision_changed = await api_client.post(
        "/imports/healthkit/batches",
        json=steps_batch(
            batch_id=uuid4(), installation_id=installation_id, count=201, source_revision=2
        ),
    )
    assert first.status_code == newest.status_code == stale.status_code == 201
    assert newest.json()["updated_count"] == 1
    assert stale.json()["unchanged_count"] == 1
    assert same_revision_changed.status_code == 409

    source_id = f"daily:2026-10-01:America/Los_Angeles:healthkit-v1:{installation_id}"
    tombstone = await api_client.post(
        "/imports/healthkit/batches",
        json={
            "batch_id": str(uuid4()),
            "device_installation_id": str(installation_id),
            "resource_type": "steps",
            "policy_version": "healthkit-v1",
            "entries": [],
            "tombstones": [{"source_sample_id": source_id, "source_revision": 3}],
        },
    )
    stale_after_delete = await api_client.post(
        "/imports/healthkit/batches",
        json=steps_batch(
            batch_id=uuid4(), installation_id=installation_id, count=300, source_revision=2
        ),
    )
    recomputed = await api_client.post(
        "/imports/healthkit/batches",
        json=steps_batch(
            batch_id=uuid4(), installation_id=installation_id, count=400, source_revision=4
        ),
    )
    assert tombstone.status_code == stale_after_delete.status_code == recomputed.status_code == 201
    assert stale_after_delete.json()["unchanged_count"] == 1
    assert recomputed.json()["updated_count"] == 1
    today = await api_client.get(
        "/today", params={"date": "2026-10-01", "timezone": "America/Los_Angeles"}
    )
    steps = next(row for row in today.json()["summaries"] if row["metric"] == "steps")
    assert steps["known_value"] == 400


@pytest.mark.asyncio
async def test_unknown_sample_tombstone_prevents_late_creation(api_client: AsyncClient) -> None:
    installation_id, sample_id = uuid4(), uuid4()
    deleted = await api_client.post(
        "/imports/healthkit/batches",
        json=workout_batch(
            batch_id=uuid4(),
            sample_id=sample_id,
            installation_id=installation_id,
            tombstones=[str(sample_id)],
        ),
    )
    late_sample = await api_client.post(
        "/imports/healthkit/batches",
        json=workout_batch(batch_id=uuid4(), sample_id=sample_id, installation_id=installation_id),
    )
    assert deleted.status_code == late_sample.status_code == 201
    assert deleted.json()["tombstoned_count"] == 1
    assert late_sample.json()["unchanged_count"] == 1
    assert (await api_client.get("/events")).json()["items"] == []


@pytest.mark.asyncio
async def test_user_archived_import_stays_inactive_and_does_not_poison_batch(
    api_client: AsyncClient,
) -> None:
    installation_id, sample_id, second_sample_id = uuid4(), uuid4(), uuid4()
    imported = await api_client.post(
        "/imports/healthkit/batches",
        json=workout_batch(batch_id=uuid4(), sample_id=sample_id, installation_id=installation_id),
    )
    assert imported.status_code == 201
    item = (await api_client.get("/events")).json()["items"][0]
    archived = await api_client.delete(
        f"/events/{item['id']}", params={"expected_revision": item["revision"]}
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    changed = workout_batch(
        batch_id=uuid4(), sample_id=sample_id, installation_id=installation_id, duration=40
    )
    changed["entries"].append(
        {
            "source_sample_id": str(second_sample_id),
            "record": workout_record(25),
            "metadata": {"source_bundle_identifier": "com.example.health"},
        }
    )
    response = await api_client.post("/imports/healthkit/batches", json=changed)
    assert response.status_code == 201
    assert response.json()["correction_count"] == 1
    assert response.json()["created_count"] == 1
    current = await api_client.get(f"/events/{item['id']}")
    assert current.status_code == 200
    assert current.json()["status"] == "archived"

    deleted = await api_client.post(
        "/imports/healthkit/batches",
        json=workout_batch(
            batch_id=uuid4(),
            sample_id=sample_id,
            installation_id=installation_id,
            tombstones=[str(sample_id)],
        ),
    )
    assert deleted.status_code == 201
    assert deleted.json()["tombstoned_count"] == 1
    assert (await api_client.get(f"/events/{item['id']}")).json()["status"] == "archived"
