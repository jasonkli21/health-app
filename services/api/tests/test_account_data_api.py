from __future__ import annotations

from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from time import time
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from health_api.application import account_data_service
from health_api.application.account_data_service import (
    AccountDataConflict,
    AccountDataNotFound,
    _owner_tables,
    begin_owner_deletion,
    export_owner_snapshot,
)
from health_api.application.profile_service import CreateProfile, create_profile_item
from health_api.config.settings import Settings
from health_api.domain.schemas import ProfilePayloadV1, ProfileValidity
from health_api.integrations.firebase_auth import VerifiedIdentity
from health_api.integrations.object_storage import ObjectCleanupPending
from health_api.main import create_app
from health_api.persistence.models import HealthObject, ProfileItem, User

OWNER_ID = UUID("00000000-0000-0000-0000-000000000901")
OTHER_OWNER_ID = UUID("00000000-0000-0000-0000-000000000902")
ROOT = Path(__file__).resolve().parents[3]


def _seed_remaining_owner_inventory(db_session: Session) -> None:
    """Add one valid synthetic row to each inventory table not made by the API flows."""
    tables = {table.name: table for table in _owner_tables()}
    profile = db_session.scalar(
        select(ProfileItem).where(ProfileItem.owner_id == OWNER_ID).limit(1)
    )
    assert profile is not None
    source_id = db_session.scalar(
        select(HealthObject.source_id).where(
            HealthObject.owner_id == OWNER_ID, HealthObject.id == profile.object_id
        )
    )
    assert source_id is not None
    now = datetime.now(UTC)

    def add_health_object(object_id: UUID, object_type: str, domain: str, title: str) -> None:
        db_session.execute(
            tables["health_objects"]
            .insert()
            .values(
                id=object_id,
                owner_id=OWNER_ID,
                object_type=object_type,
                domain=domain,
                title=title,
                source_id=source_id,
                confirmation_status="user_confirmed",
                schema_version=1,
                create_fingerprint=uuid4().hex,
            )
        )

    def add_revision(object_id: UUID, object_type: str, domain: str, title: str) -> None:
        db_session.execute(
            tables["health_object_revisions"]
            .insert()
            .values(
                owner_id=OWNER_ID,
                object_id=object_id,
                revision=1,
                actor_kind="user",
                actor_id=OWNER_ID,
                reason="create",
                snapshot={"title": title},
                daily_object_type=object_type if object_type in {"event", "observation"} else None,
                daily_domain=domain if object_type in {"event", "observation"} else None,
                daily_status="active" if object_type in {"event", "observation"} else None,
                daily_sequence=1 if object_type in {"event", "observation"} else None,
                daily_time_precision="instant" if object_type in {"event", "observation"} else None,
                daily_occurred_at=now if object_type in {"event", "observation"} else None,
            )
        )

    event_id, observation_id = uuid4(), uuid4()
    add_health_object(event_id, "event", "symptoms", "Synthetic inventory event")
    add_health_object(observation_id, "observation", "symptoms", "Synthetic inventory severity")
    add_revision(event_id, "event", "symptoms", "Synthetic inventory event")
    add_revision(observation_id, "observation", "symptoms", "Synthetic inventory severity")
    db_session.execute(
        tables["events"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            object_id=event_id,
            event_kind="symptom",
            time_precision="instant",
            occurred_at=now,
            timezone="UTC",
            payload={"kind": "symptom", "label": "Synthetic inventory event"},
        )
    )
    db_session.execute(
        tables["observations"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            object_id=observation_id,
            metric_key="symptom_severity",
            time_precision="instant",
            observed_at=now,
            timezone="UTC",
            numeric_value=5,
            unit="score",
            payload={"value": {"metric": "symptom_severity", "value": 5, "unit": "score"}},
        )
    )
    db_session.execute(
        tables["event_observation_links"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            event_object_id=event_id,
            observation_object_id=observation_id,
            role="symptom_severity",
        )
    )

    db_session.execute(
        tables["daily_snapshot_markers"].insert().values(owner_id=OWNER_ID, daily_sequence=1)
    )
    installation_id = uuid4()
    db_session.execute(
        tables["healthkit_import_batches"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            batch_id=uuid4(),
            device_installation_id=installation_id,
            resource_type="steps",
            policy_version="healthkit-v1",
            content_hash="a" * 64,
        )
    )
    db_session.execute(
        tables["healthkit_import_identities"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            resource_type="steps",
            source_sample_id="synthetic-account-data-review",
            object_id=event_id,
            device_installation_id=installation_id,
            content_hash="b" * 64,
            is_aggregate=False,
            analytics_selected=True,
            policy_version="healthkit-v1",
        )
    )
    db_session.execute(
        tables["healthkit_source_preferences"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            resource_type="steps",
            device_installation_id=installation_id,
            source_id=source_id,
        )
    )

    proposal_id = uuid4()
    db_session.execute(
        tables["action_proposals"]
        .insert()
        .values(
            id=proposal_id,
            owner_id=OWNER_ID,
            schema_version=1,
            state="pending",
            origin_kind="user",
            current_revision=1,
            content_hash="c" * 64,
            expires_at=now + timedelta(days=1),
        )
    )
    db_session.execute(
        tables["action_proposal_revisions"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            proposal_id=proposal_id,
            revision=1,
            schema_version=1,
            content_hash="c" * 64,
            snapshot={"synthetic": True},
            actor_id=OWNER_ID,
        )
    )
    db_session.execute(
        tables["action_proposal_events"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            proposal_id=proposal_id,
            proposal_revision=1,
            event="created",
            actor_id=OWNER_ID,
        )
    )
    db_session.execute(
        tables["action_command_receipts"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            proposal_id=proposal_id,
            proposal_revision=1,
            idempotency_key="synthetic-account-data-review",
            content_hash="d" * 64,
            result_json={"synthetic": True},
        )
    )

    derived_id = uuid4()
    add_health_object(derived_id, "derived_signal", "analytics", "Synthetic inventory signal")
    add_revision(derived_id, "derived_signal", "analytics", "Synthetic inventory signal")
    db_session.execute(
        tables["analytics_artifacts"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            object_id=derived_id,
            artifact_kind="derived_signal",
            state="current",
            payload={"synthetic": True},
        )
    )
    db_session.execute(
        tables["analytics_evidence"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            artifact_object_id=derived_id,
            evidence_object_id=event_id,
            evidence_revision=1,
            evidence_object_type="event",
        )
    )
    db_session.execute(
        tables["health_relationships"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            from_object_id=profile.object_id,
            to_object_id=event_id,
            relation_type="related_to",
            source_id=source_id,
        )
    )

    plan_id, tracker_id = uuid4(), uuid4()
    add_health_object(plan_id, "plan", "planning", "Synthetic inventory plan")
    add_health_object(tracker_id, "tracker_definition", "planning", "Synthetic inventory tracker")
    db_session.execute(
        tables["planning_resources"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            object_id=plan_id,
            resource_kind="plan",
            lifecycle="active",
            payload={},
        )
    )
    db_session.execute(
        tables["planning_resources"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            object_id=tracker_id,
            resource_kind="tracker_definition",
            lifecycle="active",
            current_schema_version=1,
            payload={},
        )
    )
    db_session.execute(
        tables["tracker_schema_versions"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            tracker_id=tracker_id,
            version=1,
            definition={},
        )
    )
    link_id, schedule_id = uuid4(), uuid4()
    db_session.execute(
        tables["planning_links"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            parent_object_id=plan_id,
            link_id=link_id,
            link_kind="plan_task",
            label="Synthetic scheduled task",
            position=0,
        )
    )
    db_session.execute(
        tables["planning_schedule_identities"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            schedule_id=schedule_id,
            parent_object_id=plan_id,
            item_id=link_id,
        )
    )
    db_session.execute(
        tables["planning_schedules"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            schedule_id=schedule_id,
            revision=1,
            parent_object_id=plan_id,
            item_id=link_id,
            effective_from=now.date(),
            definition={"synthetic": True},
        )
    )
    occurrence_key = "synthetic-account-data-review"
    db_session.execute(
        tables["planning_occurrence_overrides"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            occurrence_key=occurrence_key,
            schedule_id=schedule_id,
            expected_schedule_revision=1,
            state="completed",
        )
    )
    db_session.execute(
        tables["planning_occurrence_actions"]
        .insert()
        .values(
            owner_id=OWNER_ID,
            occurrence_key=occurrence_key,
            revision=1,
            action="completed",
            schedule_revision=1,
            actor_id=OWNER_ID,
        )
    )
    db_session.flush()


def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        auth_mode="dev",
        local_principal_id=OWNER_ID,
        local_principal_timezone="America/Los_Angeles",
    )


@pytest_asyncio.fixture
async def api_client(
    db_session: Session, postgres_engine: Engine
) -> AsyncIterator[tuple[AsyncClient, object]]:
    app = create_app(settings(), engine=postgres_engine)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client, app


@pytest.mark.asyncio
async def test_deletion_request_is_discoverable_and_resumes_after_local_id_loss(
    api_client: tuple[AsyncClient, object],
) -> None:
    client, app = api_client

    class PendingOnceStorage:
        calls = 0

        def delete_owner(self, _owner_id: UUID) -> None:
            self.calls += 1
            if self.calls == 1:
                raise ObjectCleanupPending

    storage = PendingOnceStorage()
    app.state.object_storage = storage  # type: ignore[attr-defined]
    request_id = uuid4()

    started = await client.post(
        "/deletion-requests",
        json={"request_id": str(request_id), "confirmation": "DELETE MY HEALTH DATA"},
    )
    assert started.status_code == 202
    assert started.json()["status"] == "running"

    frozen_write = await client.post(
        "/profile",
        json={
            "id": str(uuid4()),
            "profile": {
                "kind": "fact",
                "category": "background",
                "key": "frozen_write_probe",
                "label": "Synthetic freeze probe",
                "value": {"type": "text", "value": "must not persist"},
            },
            "valid_from": None,
            "valid_to": None,
            "ai_use_allowed": False,
            "cross_domain_use_allowed": False,
            "notes": None,
            "metadata": {},
        },
    )
    assert frozen_write.status_code == 401
    assert frozen_write.json()["code"] == "principal_unavailable"

    discovered = await client.get("/deletion-requests/current")
    assert discovered.status_code == 200
    assert discovered.json()["request_id"] == str(request_id)
    assert discovered.json()["status"] == "running"

    conflicting = await client.post(
        "/deletion-requests",
        json={"request_id": str(uuid4()), "confirmation": "DELETE MY HEALTH DATA"},
    )
    assert conflicting.status_code == 409
    assert conflicting.json()["code"] == "deletion_conflict"

    resumed = await client.post(
        "/deletion-requests",
        json={"request_id": str(request_id), "confirmation": "DELETE MY HEALTH DATA"},
    )
    assert resumed.status_code == 202
    assert resumed.json()["status"] == "completed"
    assert (await client.get("/deletion-requests/current")).json()["status"] == "completed"
    assert storage.calls == 2


@pytest.mark.asyncio
async def test_export_and_erasure_are_owner_scoped_across_the_inventory(
    api_client: tuple[AsyncClient, object],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    postgres_engine: Engine,
) -> None:
    client, _app = api_client
    created = await client.post(
        "/profile",
        json={
            "id": str(uuid4()),
            "profile": {
                "kind": "fact",
                "category": "background",
                "key": "review_test_fact",
                "label": "Synthetic café account data fixture",
                "value": {"type": "text", "value": "owner-a-only"},
            },
            "valid_from": None,
            "valid_to": None,
            "ai_use_allowed": False,
            "cross_domain_use_allowed": False,
            "notes": None,
            "metadata": {},
        },
    )
    assert created.status_code == 201

    db_session.add(User(id=OTHER_OWNER_ID, display_timezone="UTC"))
    db_session.commit()
    create_profile_item(
        db_session,
        OTHER_OWNER_ID,
        CreateProfile(
            id=uuid4(),
            profile=ProfilePayloadV1.model_validate(
                {
                    "kind": "fact",
                    "category": "background",
                    "key": "review_test_fact",
                    "label": "Synthetic account data fixture",
                    "value": {"type": "text", "value": "owner-b-only"},
                }
            ),
            validity=ProfileValidity(),
        ),
    )
    db_session.commit()
    _seed_remaining_owner_inventory(db_session)
    db_session.commit()

    expected_tables = {table.name for table in _owner_tables()}
    populated_tables = {
        table.name
        for table in _owner_tables()
        if db_session.scalar(
            select(func.count()).select_from(table).where(table.c.owner_id == OWNER_ID)
        )
        > 0
    }
    assert populated_tables == expected_tables
    db_session.commit()

    full_snapshot = export_owner_snapshot(db_session, OWNER_ID)
    assert len(full_snapshot.encode("utf-8")) > len(full_snapshot)
    with monkeypatch.context() as limits:
        limits.setattr(
            "health_api.application.account_data_service._EXPORT_ROW_LIMIT",
            len(expected_tables),
        )
        too_many_rows = await client.get("/exports/current")
        assert too_many_rows.status_code == 413
        assert "owner-a-only" not in too_many_rows.text

    with monkeypatch.context() as limits:
        limits.setattr(
            "health_api.application.account_data_service._EXPORT_BYTE_LIMIT",
            len(full_snapshot),
        )
        too_many_bytes = await client.get("/exports/current")
        assert too_many_bytes.status_code == 413
        assert "owner-a-only" not in too_many_bytes.text

    exported = await client.get("/exports/current")
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["owner"]["id"] == str(OWNER_ID)
    assert payload["manifest"]["total_rows"] >= len(expected_tables)
    assert set(payload["manifest"]["table_row_counts"]) == expected_tables
    assert all(count > 0 for count in payload["manifest"]["table_row_counts"].values())
    assert all(
        row["owner_id"] == str(OWNER_ID)
        for table_rows in payload["data"].values()
        for row in table_rows
    )
    assert "owner-b-only" not in exported.text

    request_id = uuid4()
    deleted = await client.post(
        "/deletion-requests",
        json={"request_id": str(request_id), "confirmation": "DELETE MY HEALTH DATA"},
    )
    assert deleted.status_code == 202
    assert deleted.json()["status"] == "completed"
    db_session.expire_all()

    for table in _owner_tables():
        remaining = db_session.scalar(
            select(func.count()).select_from(table).where(table.c.owner_id == OWNER_ID)
        )
        assert remaining == 0, table.name
    other_profile_rows = db_session.scalar(
        select(func.count()).select_from(ProfileItem).where(ProfileItem.owner_id == OTHER_OWNER_ID)
    )
    assert other_profile_rows == 1

    db_session.commit()
    config = Config(str(ROOT / "alembic.ini"))
    with postgres_engine.begin() as connection:
        config.attributes["connection"] = connection
        with pytest.raises(RuntimeError, match="refusing to remove owner erasure state"):
            command.downgrade(config, "20261006b1a2")


def test_export_uses_one_repeatable_read_snapshot_during_a_concurrent_edit(
    db_session: Session,
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_session.add(User(id=OWNER_ID, display_timezone="UTC"))
    profile_id = uuid4()
    create_profile_item(
        db_session,
        OWNER_ID,
        CreateProfile(
            id=profile_id,
            profile=ProfilePayloadV1.model_validate(
                {
                    "kind": "fact",
                    "category": "background",
                    "key": "snapshot_probe",
                    "label": "Synthetic snapshot probe",
                    "value": {"type": "text", "value": "before"},
                }
            ),
            validity=ProfileValidity(),
        ),
    )
    db_session.commit()

    snapshot_started, mutation_committed = Event(), Event()

    def pause_after_snapshot_start():
        snapshot_started.set()
        if not mutation_committed.wait(timeout=5):
            raise TimeoutError("concurrent edit did not finish")
        yield ProfileItem.__table__

    monkeypatch.setattr(account_data_service, "_owner_tables", pause_after_snapshot_start)
    factory = sessionmaker(bind=postgres_engine, expire_on_commit=False)

    def export() -> str:
        with factory() as session:
            return export_owner_snapshot(session, OWNER_ID)

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(export)
        assert snapshot_started.wait(timeout=5)
        try:
            with factory.begin() as writer:
                writer.execute(
                    update(ProfileItem)
                    .where(
                        ProfileItem.owner_id == OWNER_ID,
                        ProfileItem.object_id == profile_id,
                    )
                    .values(
                        payload={
                            "kind": "fact",
                            "category": "background",
                            "key": "snapshot_probe",
                            "value": {"type": "text", "value": "after"},
                        }
                    )
                )
        finally:
            mutation_committed.set()
        snapshot = result.result(timeout=5)

    assert '"value":"before"' in snapshot
    assert '"value":"after"' not in snapshot


def test_identical_deletion_starts_serialize_and_foreign_id_collision_is_hidden(
    db_session: Session, postgres_engine: Engine
) -> None:
    owner_a, owner_b, request_id = uuid4(), uuid4(), uuid4()
    db_session.add_all(
        [
            User(id=owner_a, display_timezone="UTC"),
            User(id=owner_b, display_timezone="UTC"),
        ]
    )
    db_session.commit()
    factory = sessionmaker(bind=postgres_engine, expire_on_commit=False)

    def start() -> tuple[UUID, str]:
        with factory() as session:
            job = begin_owner_deletion(session, owner_a, request_id)
            return job.id, job.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: start(), range(2)))
    assert results == [(request_id, "running"), (request_id, "running")]

    with factory() as session, pytest.raises(AccountDataConflict):
        begin_owner_deletion(session, owner_a, uuid4())
    with factory() as session, pytest.raises(AccountDataNotFound):
        begin_owner_deletion(session, owner_b, request_id)


def test_recent_authentication_gates_discovery_and_same_request_resumes(
    db_session: Session,
    postgres_engine: Engine,
) -> None:
    class MutableVerifier:
        auth_time: int | None = int(time())

        def verify(self, _token: str) -> VerifiedIdentity:
            return VerifiedIdentity(
                issuer="https://securetoken.google.com/health-test",
                subject="account-data-review-subject",
                auth_time=self.auth_time,
            )

    verifier = MutableVerifier()
    config = Settings(
        _env_file=None,
        app_env="test",
        auth_mode="firebase",
        firebase_project_id="health-test",
    )
    client = TestClient(create_app(config, engine=postgres_engine, identity_verifier=verifier))
    headers = {"Authorization": "Bearer synthetic-token"}
    request_id = uuid4()

    verifier.auth_time = None
    missing_time = client.get("/deletion-requests/current", headers=headers)
    assert missing_time.status_code == 401
    assert missing_time.json()["code"] == "recent_authentication_required"

    verifier.auth_time = int(time()) - 301
    old_time = client.get("/deletion-requests/current", headers=headers)
    assert old_time.status_code == 401
    assert old_time.json()["code"] == "recent_authentication_required"

    verifier.auth_time = int(time()) + 61
    future_time = client.get("/deletion-requests/current", headers=headers)
    assert future_time.status_code == 401
    assert future_time.json()["code"] == "recent_authentication_required"

    stale_start = client.post(
        "/deletion-requests",
        headers=headers,
        json={"request_id": str(request_id), "confirmation": "DELETE MY HEALTH DATA"},
    )
    assert stale_start.status_code == 401
    assert stale_start.json()["code"] == "recent_authentication_required"

    verifier.auth_time = int(time())
    resumed = client.post(
        "/deletion-requests",
        headers=headers,
        json={"request_id": str(request_id), "confirmation": "DELETE MY HEALTH DATA"},
    )
    assert resumed.status_code == 202
    assert resumed.json()["request_id"] == str(request_id)
    assert resumed.json()["status"] == "completed"
