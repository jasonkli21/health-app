from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from health_api.application import planning_schedules
from health_api.application import planning_service as planning
from health_api.application.errors import PlanningConflict, PlanningNotFound
from health_api.application.local_principal import ensure_local_principal
from health_api.config.settings import Settings
from health_api.domain.planning import PlanPayloadV1, RegimenPayloadV1, ScheduleDefinitionV1
from health_api.domain.scheduling import expand_schedule, resolve_local_time
from health_api.persistence.models import (
    PlanningLink,
    PlanningOccurrenceOverride,
    PlanningSchedule,
    PlanningScheduleIdentity,
)
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, MetaData, create_engine, select
from sqlalchemy.orm import Session


def test_retired_manual_task_constraint_and_repeated_reorder() -> None:
    # Exercise the actual ORM writes and portable CHECK/UNIQUE constraints.
    # This deliberately does not replace PostgreSQL FK/migration acceptance.
    metadata = MetaData()
    for model in (PlanningLink, PlanningScheduleIdentity):
        table = model.__table__.to_metadata(metadata)
        for constraint in list(table.constraints):
            if isinstance(constraint, ForeignKeyConstraint):
                table.constraints.remove(constraint)
                for foreign_key in constraint.elements:
                    table.foreign_keys.remove(foreign_key)
                    foreign_key.parent.foreign_keys.remove(foreign_key)
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    owner, parent, task_id, other_id = uuid4(), uuid4(), uuid4(), uuid4()
    with Session(engine) as session:
        session.add_all(
            [
                PlanningLink(
                    owner_id=owner,
                    parent_object_id=parent,
                    link_id=item_id,
                    link_kind="plan_task",
                    target_object_id=None,
                    label="Task",
                    position=position,
                    priority=0,
                )
                for position, item_id in enumerate((task_id, other_id))
            ]
        )
        session.add(
            PlanningScheduleIdentity(
                owner_id=owner,
                schedule_id=uuid4(),
                parent_object_id=parent,
                item_id=task_id,
            )
        )
        session.commit()
        payload = PlanPayloadV1(
            label="Plan",
            items=[
                {"id": other_id, "kind": "task", "label": "Remaining task"},
            ],
        )
        planning._sync_links(session, owner, parent, "plan", payload)
        session.commit()
        retired = session.get(PlanningLink, (owner, parent, task_id))
        assert retired is not None and retired.link_kind == "plan_retired"
        assert retired.target_object_id is None
        # Positions >= 100 are now occupied by history. Two more updates used
        # to collide while moving current positions into that same range.
        for _ in range(2):
            planning._sync_links(session, owner, parent, "plan", payload)
            session.commit()
        rows = list(session.scalars(select(PlanningLink)))
        assert len({row.position for row in rows}) == len(rows) == 2
    engine.dispose()


def test_retired_task_check_still_rejects_missing_live_reference() -> None:
    constraint = next(
        c
        for c in PlanningLink.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_planning_links_target"
    )
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        for kind, target, expected in (
            ("plan_retired", None, 1),
            ("plan_task", None, 1),
            ("plan_goal", None, 0),
            ("plan_goal", "goal-id", 1),
            ("plan_task", "goal-id", 0),
        ):
            result = connection.exec_driver_sql(
                f"SELECT {constraint.sqltext} FROM (SELECT ? AS link_kind, ? AS target_object_id)",
                (kind, target),
            ).scalar_one()
            assert result == expected
    engine.dispose()


@pytest.mark.parametrize("state", ["completed", "skipped", "rescheduled"])
def test_recorded_occurrence_can_change_after_schedule_edit(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    owner, parent, schedule = uuid4(), uuid4(), uuid4()
    day = date(2026, 10, 12)
    definition = ScheduleDefinitionV1(
        start_date=date(2026, 10, 1),
        local_time=time(8),
        timezone="UTC",
        recurrence="daily",
    )
    version = NS(revision=1, definition=definition.model_dump(mode="json"))
    key = planning._schedule_key(schedule, day, "08:00:00")
    moved = datetime(2026, 10, 13, 9, tzinfo=UTC)
    current = NS(
        expected_schedule_revision=1,
        override_revision=1,
        state="rescheduled",
        rescheduled_at=moved,
        original_due_at=None,
        original_timezone=None,
        dst_resolution=None,
        linked_event_id=None,
        linked_observation_id=uuid4(),
        updated_at=datetime.now(UTC),
    )
    session = MagicMock()
    session.begin.return_value = nullcontext()
    session.execute.return_value.one_or_none.return_value = (
        NS(status="active"),
        NS(lifecycle="active"),
    )
    identity = NS(parent_object_id=parent, item_id=None, retired_at=None)

    def lookup(model: object, identity_key: object) -> object:
        if model is PlanningScheduleIdentity:
            return identity
        if model is PlanningOccurrenceOverride:
            return current
        assert model is PlanningSchedule and identity_key == (owner, schedule, 1)
        return version

    session.get.side_effect = lookup
    monkeypatch.setattr(planning_schedules, "_occurrence_is_eligible", lambda *args: True)
    # The latest version is revision 2 and a different time. Existing recorded
    # keys must never be looked up through the new effective version.
    latest = MagicMock(side_effect=AssertionError("used latest schedule for recorded key"))
    monkeypatch.setattr(planning_schedules, "_schedule_row_for_date", latest)
    next_due = moved + timedelta(days=1) if state == "rescheduled" else None
    result = planning.record_occurrence_action(
        session,
        owner,
        key,
        1,
        1,
        state,
        next_due,
        None,
    )
    assert result["linked_observation_id"] == current.linked_observation_id
    assert result["state"] == state
    assert result["schedule_revision"] == 1
    assert result["rescheduled_at"] == (next_due or moved)
    assert current.original_due_at == datetime(2026, 10, 12, 8, tzinfo=UTC)
    assert current.original_timezone == "UTC"
    assert current.dst_resolution == "exact"


@pytest.mark.parametrize(
    "local_value,expected,resolution",
    [
        (
            datetime.fromisoformat("2027-03-14T02:30:00"),
            datetime(2027, 3, 14, 10, tzinfo=UTC),
            "next_valid_time",
        ),
        (
            datetime.fromisoformat("2026-11-01T01:30:00"),
            datetime(2026, 11, 1, 8, 30, tzinfo=UTC),
            "earlier_offset",
        ),
    ],
)
def test_dst_slots_resolve_once(local_value: datetime, expected: datetime, resolution: str) -> None:
    assert resolve_local_time(local_value, "America/Los_Angeles") == (expected, resolution)


@pytest.mark.parametrize(
    "definition,start,end,expected",
    [
        (
            {"start_date": "2026-10-05", "recurrence": "daily", "interval": 2},
            date(2026, 10, 5),
            date(2026, 10, 10),
            [5, 7, 9],
        ),
        (
            {"start_date": "2026-10-05", "recurrence": "weekly", "interval": 2, "weekdays": [1]},
            date(2026, 10, 5),
            date(2026, 10, 25),
            [6, 20],
        ),
        (
            {"start_date": "2028-02-27", "recurrence": "daily"},
            date(2028, 2, 27),
            date(2028, 2, 29),
            [27, 28, 29],
        ),
    ],
)
def test_recurrence_calendar_fixtures(
    definition: dict, start: date, end: date, expected: list[int]
) -> None:
    schema = ScheduleDefinitionV1.model_validate(
        {**definition, "local_time": "08:00:00", "timezone": "UTC"}
    )
    slots = expand_schedule(
        schema, start, end, schedule_id="s", revision=1, parent_id="p", item_id=None
    )
    assert [slot["local_date"].day for slot in slots] == expected


def principal(session: Session) -> UUID:
    owner = uuid4()
    assert (
        ensure_local_principal(
            session, Settings(app_env="test", auth_mode="dev", local_principal_id=owner)
        )
        == owner
    )
    return owner


def test_postgres_recorded_item_survives_edit_retirement_and_archive(db_session: Session) -> None:
    owner = principal(db_session)
    plan_id, task_id = uuid4(), uuid4()
    today = datetime.now(UTC).date()
    day = today + timedelta(days=2)
    payload = PlanPayloadV1(label="Plan", items=[{"id": task_id, "kind": "task", "label": "Task"}])
    planning.create_planning_resource(db_session, owner, plan_id, "plan", payload)
    original = ScheduleDefinitionV1(
        start_date=today, local_time=time(8), timezone="UTC", recurrence="daily"
    )
    schedule = planning.set_planning_schedule(
        db_session, owner, plan_id, "plan", task_id, None, today, original
    )
    key = planning._schedule_key(schedule["schedule_id"], day, "08:00:00")
    moved = datetime.combine(day + timedelta(days=1), time(10), tzinfo=UTC)
    planning.record_occurrence_action(db_session, owner, key, 1, None, "rescheduled", moved, None)
    changed = original.model_copy(update={"local_time": time(9)})
    planning.set_planning_schedule(
        db_session, owner, plan_id, "plan", task_id, 1, today + timedelta(days=1), changed
    )
    result = planning.record_occurrence_action(
        db_session, owner, key, 1, 1, "completed", None, None
    )
    assert result["rescheduled_at"] == moved
    row = planning.get_planning_resource(db_session, owner, plan_id)
    revision = row[0].revision
    db_session.rollback()  # close the read transaction before the command
    planning.update_planning_resource(
        db_session, owner, plan_id, "plan", revision, PlanPayloadV1(label="Plan", items=[])
    )
    row = planning.get_planning_resource(db_session, owner, plan_id)
    revision = row[0].revision
    db_session.rollback()
    planning.archive_planning_resource(db_session, owner, plan_id, "plan", revision)
    occurrences, _ = planning.load_today_planning(db_session, owner, moved.date(), "UTC")
    assert [(item["key"], item["state"], item["due_at"]) for item in occurrences] == [
        (key, "completed", moved)
    ]
    assert occurrences[0]["can_act"] is False
    assert len(planning.list_occurrence_history(db_session, owner, key, 0, 10)) == 2
    db_session.rollback()
    with pytest.raises(PlanningNotFound):
        planning.list_planning_occurrences(db_session, uuid4(), plan_id, "plan", day, day, "UTC")


def test_postgres_task_retirement_keeps_links_and_rejects_schedule_reactivation(
    db_session: Session,
) -> None:
    owner = principal(db_session)
    plan_id, task_id = uuid4(), uuid4()
    today = datetime.now(UTC).date()
    payload = PlanPayloadV1(label="Plan", items=[{"id": task_id, "kind": "task", "label": "Task"}])
    planning.create_planning_resource(db_session, owner, plan_id, "plan", payload)
    definition = ScheduleDefinitionV1(
        start_date=today, local_time=time(8), timezone="UTC", recurrence="daily"
    )
    planning.set_planning_schedule(
        db_session, owner, plan_id, "plan", task_id, None, today, definition
    )
    planning.update_planning_resource(
        db_session, owner, plan_id, "plan", 2, PlanPayloadV1(label="Plan", items=[])
    )
    link = db_session.get(PlanningLink, (owner, plan_id, task_id))
    assert link is not None and link.link_kind == "plan_retired" and link.target_object_id is None
    db_session.rollback()
    with pytest.raises((PlanningConflict, PlanningNotFound)):
        planning.set_planning_schedule(
            db_session, owner, plan_id, "plan", task_id, 1, today + timedelta(days=1), definition
        )


def test_postgres_today_uses_schedule_timezone_for_validity(db_session: Session) -> None:
    owner = principal(db_session)
    regimen_id = uuid4()
    today = datetime.now(UTC).date()
    day = today + timedelta(days=2)
    payload = RegimenPayloadV1(label="Evening", kind="habit", start_date=day, end_date=day)
    planning.create_planning_resource(db_session, owner, regimen_id, "regimen", payload)
    definition = ScheduleDefinitionV1(
        start_date=day, local_time=time(23), timezone="America/Los_Angeles", recurrence="daily"
    )
    planning.set_planning_schedule(
        db_session, owner, regimen_id, "regimen", None, None, today, definition
    )
    items, _ = planning.load_today_planning(db_session, owner, day + timedelta(days=1), "UTC")
    assert len(items) == 1 and items[0]["original_local_date"] == day
