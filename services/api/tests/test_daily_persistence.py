from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from health_api.application import daily_service
from health_api.application.daily_service import (
    CreateDailyEntry,
    CreateDailyEvent,
    CreateDailyLink,
    CreateDailyObservation,
    archive_daily_item,
    create_daily_entry,
    get_daily_item,
    list_daily_history,
    update_daily_item,
)
from health_api.application.errors import DailyConflict, DailyNotFound
from health_api.application.local_principal import ensure_local_principal
from health_api.config.settings import Settings
from health_api.domain.schemas import EventSchemaV1, ObservationSchemaV1
from health_api.persistence.models import (
    DailySnapshotMarker,
    EventItem,
    EventObservationLink,
    HealthObject,
    HealthObjectRevision,
    ObservationItem,
    Source,
    User,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker


def new_principal(session: Session, principal_id: UUID | None = None) -> UUID:
    identity = principal_id or uuid4()
    settings = Settings(
        app_env="test",
        auth_mode="dev",
        local_principal_id=identity,
    )
    assert ensure_local_principal(session, settings) == identity
    return identity


def instant(at: datetime | None = None) -> dict[str, object]:
    return {
        "precision": "instant",
        "occurred_at": at or datetime(2026, 10, 3, 18, tzinfo=UTC),
        "timezone": "America/Los_Angeles",
    }


def meal_event(label: str = "Lunch", at: datetime | None = None) -> EventSchemaV1:
    return EventSchemaV1.model_validate(
        {
            "domain": "nutrition",
            "time": instant(at),
            "payload": {"kind": "meal", "label": label, "energy": {"value": 0, "unit": "kcal"}},
        }
    )


def symptom_event() -> EventSchemaV1:
    return EventSchemaV1.model_validate(
        {
            "domain": "symptoms",
            "time": instant(),
            "payload": {"kind": "symptom", "label": "Headache"},
        }
    )


def measurement(
    metric: str = "weight",
    value: int = 70,
    unit: str = "kg",
    *,
    at: datetime | None = None,
) -> ObservationSchemaV1:
    return ObservationSchemaV1.model_validate(
        {
            "domain": "measurements",
            "time": instant(at),
            "payload": {"value": {"metric": metric, "value": value, "unit": unit}},
        }
    )


def symptom_severity(value: int = 4) -> ObservationSchemaV1:
    return ObservationSchemaV1.model_validate(
        {
            "domain": "symptoms",
            "time": instant(),
            "payload": {"value": {"metric": "symptom_severity", "value": value}},
        }
    )


def test_compound_symptom_save_is_idempotent_and_records_manual_history(
    db_session: Session,
) -> None:
    owner = new_principal(db_session)
    event_id, observation_id = uuid4(), uuid4()
    command = CreateDailyEntry(
        events=(CreateDailyEvent(event_id, symptom_event()),),
        observations=(CreateDailyObservation(observation_id, symptom_severity()),),
        links=(CreateDailyLink(event_id, observation_id),),
    )

    created = create_daily_entry(db_session, owner, command)
    assert created.created is True
    event = created.events[0]
    observation = created.observations[0]
    assert event[0].confirmation_status == "user_confirmed"
    assert event[0].ai_use_allowed is False
    assert event[0].cross_domain_use_allowed is False
    assert event[2].source_kind == observation[2].source_kind == "manual"
    assert event[3] == (observation_id,)
    assert observation[1].numeric_value == 4

    retry = create_daily_entry(db_session, owner, command)
    assert retry.created is False
    assert retry.events[0][0].revision == retry.observations[0][0].revision == 1
    assert db_session.scalar(select(User.daily_sequence).where(User.id == owner)) == 1
    revisions = list(
        db_session.scalars(
            select(HealthObjectRevision)
            .where(HealthObjectRevision.owner_id == owner)
            .order_by(HealthObjectRevision.daily_sequence)
        )
    )
    assert [item.daily_sequence for item in revisions] == [1, 1]
    assert db_session.scalars(
        select(DailySnapshotMarker.daily_sequence).where(DailySnapshotMarker.owner_id == owner)
    ).all() == [1]
    assert revisions[0].snapshot["linked_observation_ids"] == [str(observation_id)]
    assert revisions[1].daily_object_type == "observation"
    db_session.commit()

    changed_command = CreateDailyEntry(
        events=(CreateDailyEvent(event_id, symptom_event()),),
        observations=(CreateDailyObservation(observation_id, symptom_severity(5)),),
        links=(CreateDailyLink(event_id, observation_id),),
    )
    with pytest.raises(DailyConflict):
        create_daily_entry(db_session, owner, changed_command)


def test_measurement_pair_is_one_compound_save_and_date_only_stays_date_only(
    db_session: Session,
) -> None:
    owner = new_principal(db_session)
    systolic_id, diastolic_id = uuid4(), uuid4()
    result = create_daily_entry(
        db_session,
        owner,
        CreateDailyEntry(
            observations=(
                CreateDailyObservation(systolic_id, measurement("systolic_pressure", 120, "mmHg")),
                CreateDailyObservation(diastolic_id, measurement("diastolic_pressure", 80, "mmHg")),
            )
        ),
    )
    assert result.created
    assert [row[1].metric_key for row in result.observations] == [
        "systolic_pressure",
        "diastolic_pressure",
    ]
    assert db_session.scalar(select(User.daily_sequence).where(User.id == owner)) == 1
    db_session.commit()

    date_only = ObservationSchemaV1.model_validate(
        {
            "domain": "measurements",
            "time": {
                "precision": "date_only",
                "local_date": date(2026, 10, 3),
                "timezone": "America/Los_Angeles",
            },
            "payload": {"value": {"metric": "weight", "value": 70, "unit": "kg"}},
        }
    )
    exactness_id = uuid4()
    create_daily_entry(
        db_session,
        owner,
        CreateDailyEntry(observations=(CreateDailyObservation(exactness_id, date_only),)),
    )
    stored = db_session.get(ObservationItem, (owner, exactness_id))
    assert stored is not None
    assert stored.local_date == date(2026, 10, 3)
    assert stored.observed_at is None
    history = list_daily_history(db_session, owner, exactness_id, 0, 10)
    assert history[0].snapshot["time"] == {
        "precision": "date_only",
        "local_date": "2026-10-03",
        "timezone": "America/Los_Angeles",
    }


def test_failed_compound_history_write_rolls_back_every_row_and_sequence(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = new_principal(db_session)
    event_id, observation_id = uuid4(), uuid4()
    command = CreateDailyEntry(
        events=(CreateDailyEvent(event_id, symptom_event()),),
        observations=(CreateDailyObservation(observation_id, symptom_severity()),),
        links=(CreateDailyLink(event_id, observation_id),),
    )

    def fail_revision(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic revision failure")

    monkeypatch.setattr(daily_service, "_append_event_revision", fail_revision)
    with pytest.raises(RuntimeError, match="revision failure"):
        create_daily_entry(db_session, owner, command)

    assert db_session.scalar(select(func.count()).select_from(HealthObject)) == 0
    assert db_session.scalar(select(func.count()).select_from(EventItem)) == 0
    assert db_session.scalar(select(func.count()).select_from(ObservationItem)) == 0
    assert db_session.scalar(select(func.count()).select_from(EventObservationLink)) == 0
    assert db_session.scalar(select(func.count()).select_from(HealthObjectRevision)) == 0
    assert db_session.scalar(select(User.daily_sequence).where(User.id == owner)) == 0
    assert db_session.scalar(select(func.count()).select_from(DailySnapshotMarker)) == 0
    assert db_session.scalar(select(func.count()).select_from(Source)) == 0


def test_update_archive_append_revisions_reject_stale_writes_and_retries_keep_current(
    db_session: Session,
) -> None:
    owner = new_principal(db_session)
    event_id, observation_id = uuid4(), uuid4()
    original = CreateDailyEntry(
        events=(CreateDailyEvent(event_id, symptom_event()),),
        observations=(CreateDailyObservation(observation_id, symptom_severity()),),
        links=(CreateDailyLink(event_id, observation_id),),
    )
    create_daily_entry(db_session, owner, original)
    changed = update_daily_item(db_session, owner, observation_id, 1, symptom_severity(7))
    assert isinstance(changed[1], ObservationItem)
    assert changed[1].numeric_value == 7
    assert changed[0].revision == 2
    assert changed[1].payload["value"]["value"] == 7

    with pytest.raises(DailyConflict, match="changed"):
        update_daily_item(db_session, owner, observation_id, 1, symptom_severity(8))

    retried = create_daily_entry(db_session, owner, original)
    assert retried.created is False
    assert retried.observations[0][0].revision == 2
    assert retried.observations[0][1].numeric_value == 7

    archived = archive_daily_item(db_session, owner, event_id, 1)
    assert archived[0].status == "archived"
    assert archived[0].revision == 2
    history = list_daily_history(db_session, owner, event_id, 0, 10)
    assert [item.revision for item in history] == [1, 2]
    assert [item.daily_sequence for item in history] == [1, 3]
    assert [item.snapshot["status"] for item in history] == ["active", "archived"]


def test_foreign_daily_ids_are_hidden_and_composite_links_reject_cross_owner_rows(
    db_session: Session,
) -> None:
    owner_a = new_principal(db_session)
    owner_b = new_principal(db_session)
    event_id = uuid4()
    event = create_daily_entry(
        db_session,
        owner_a,
        CreateDailyEntry(events=(CreateDailyEvent(event_id, meal_event()),)),
    )
    foreign_observation_id = uuid4()
    create_daily_entry(
        db_session,
        owner_b,
        CreateDailyEntry(
            observations=(CreateDailyObservation(foreign_observation_id, measurement()),)
        ),
    )
    with pytest.raises(DailyNotFound):
        get_daily_item(db_session, owner_a, foreign_observation_id)
    with pytest.raises(DailyNotFound):
        list_daily_history(db_session, owner_a, foreign_observation_id, 0, 10)

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            EventObservationLink(
                owner_id=owner_a,
                event_object_id=event.events[0][0].id,
                observation_object_id=foreign_observation_id,
                role="symptom_severity",
            )
        )
        db_session.flush()


def test_concurrent_daily_edits_allow_only_one_revision(db_session: Session) -> None:
    owner = new_principal(db_session)
    object_id = uuid4()
    create_daily_entry(
        db_session,
        owner,
        CreateDailyEntry(events=(CreateDailyEvent(object_id, meal_event()),)),
    )
    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    barrier = Barrier(2)

    def edit(label: str) -> str:
        with session_factory() as session:
            barrier.wait(timeout=10)
            try:
                update_daily_item(session, owner, object_id, 1, meal_event(label))
                return "updated"
            except DailyConflict:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(edit, ["Breakfast", "Dinner"]))
    assert sorted(outcomes) == ["conflict", "updated"]
    db_session.expire_all()
    aggregate = get_daily_item(db_session, owner, object_id)
    assert aggregate[0].revision == 2
    assert [row.revision for row in list_daily_history(db_session, owner, object_id, 0, 10)] == [
        1,
        2,
    ]
    assert db_session.scalars(
        select(DailySnapshotMarker.daily_sequence)
        .where(DailySnapshotMarker.owner_id == owner)
        .order_by(DailySnapshotMarker.daily_sequence)
    ).all() == [1, 2]
