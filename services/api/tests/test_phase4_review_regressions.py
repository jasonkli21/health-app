from __future__ import annotations

import base64
import json
from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.orm import configure_mappers

from health_api.api.schemas import (
    GoalCreateRequest,
    OccurrenceActionRequest,
    ScheduleEditRequest,
)
from health_api.application.errors import PlanningNotFound, PlanningValidationError
from health_api.application.planning_service import (
    _canonical,
    _occurrence_is_eligible,
    _parse_schedule_key,
    _recorded_occurrence_details,
    _schedule_key,
    _validate_references,
    list_planning_occurrences,
)
from health_api.domain.planning import (
    GoalPayloadV1,
    PlanPayloadV1,
    ScheduleDefinitionV1,
    TrackerDefinitionV1,
    validate_tracker_values,
)
from health_api.persistence.models import ObservationItem


def test_all_mappers_configure_with_the_observation_tracker_fk() -> None:
    configure_mappers()


def test_absent_tracker_values_bind_as_sql_null() -> None:
    column_type = ObservationItem.__table__.c.tracker_values.type
    processor = column_type.bind_processor(dialect())

    assert column_type.none_as_null is True
    assert processor is None or processor(None) is None


def test_schedule_edit_keeps_original_recurrence_anchor_before_effective_boundary() -> None:
    request = ScheduleEditRequest.model_validate(
        {
            "expected_schedule_revision": 1,
            "effective_from": "2026-10-06",
            "schedule": {
                "start_date": "2026-10-01",
                "local_time": "08:00:00",
                "timezone": "UTC",
                "recurrence": "daily",
            },
        }
    )

    assert request.schedule.start_date == date(2026, 10, 1)


def test_schedule_key_parser_rejects_noncanonical_aliases() -> None:
    schedule_id = uuid4()
    slot_date = date(2026, 10, 5)
    canonical = _schedule_key(schedule_id, slot_date, "08:00:00")
    assert _parse_schedule_key(canonical) == (schedule_id, slot_date, "08:00:00")

    with pytest.raises(PlanningNotFound):
        _parse_schedule_key(canonical + "=")

    alternate_json = json.dumps(
        {"s": str(schedule_id), "t": "08:00:00", "d": slot_date.isoformat()},
        indent=1,
    ).encode()
    alias = base64.urlsafe_b64encode(alternate_json).decode().rstrip("=")
    with pytest.raises(PlanningNotFound):
        _parse_schedule_key(alias)

    wrong_type = (
        base64.urlsafe_b64encode(
            _canonical({"d": slot_date.isoformat(), "s": 42, "t": "08:00:00"}).encode()
        )
        .decode()
        .rstrip("=")
    )
    with pytest.raises(PlanningNotFound):
        _parse_schedule_key(wrong_type)


def test_schedule_and_occurrence_calendar_underflow_return_validation_errors() -> None:
    with pytest.raises(ValidationError):
        ScheduleDefinitionV1.model_validate(
            {
                "start_date": "0001-01-01",
                "local_time": time(8),
                "timezone": "UTC",
                "recurrence": "daily",
            }
        )

    with pytest.raises(PlanningValidationError):
        list_planning_occurrences(
            SimpleNamespace(), uuid4(), uuid4(), "plan", date.min, date.min, "UTC"
        )


def test_legacy_completed_occurrence_uses_its_immutable_schedule_revision() -> None:
    schedule_id = uuid4()
    parent_id = uuid4()
    definition = {
        "start_date": "2026-10-01",
        "local_time": "08:00:00",
        "timezone": "UTC",
        "recurrence": "daily",
        "interval": 1,
    }
    override = SimpleNamespace(
        occurrence_key=_schedule_key(schedule_id, date(2026, 10, 5), "08:00:00"),
        expected_schedule_revision=1,
        original_timezone=None,
        dst_resolution=None,
        original_due_at=None,
        rescheduled_at=None,
    )
    versions = [
        SimpleNamespace(revision=1, definition=definition),
        SimpleNamespace(
            revision=2,
            effective_from=date(2026, 10, 6),
            definition={**definition, "local_time": "09:00:00"},
        ),
    ]

    details = _recorded_occurrence_details(override, versions, schedule_id, parent_id, None)

    assert details == (
        date(2026, 10, 5),
        "08:00:00",
        datetime(2026, 10, 5, 8, tzinfo=UTC),
        "UTC",
        "exact",
    )


def test_completed_moved_occurrence_keeps_its_destination_instant() -> None:
    schedule_id = uuid4()
    parent_id = uuid4()
    override = SimpleNamespace(
        occurrence_key=_schedule_key(schedule_id, date(2026, 10, 5), "08:00:00"),
        expected_schedule_revision=1,
        original_timezone="UTC",
        dst_resolution="exact",
        original_due_at=datetime(2026, 10, 5, 8, tzinfo=UTC),
        rescheduled_at=datetime(2026, 10, 12, 10, tzinfo=UTC),
    )

    details = _recorded_occurrence_details(override, [], schedule_id, parent_id, None)

    assert details is not None
    assert details[0:2] == (date(2026, 10, 5), "08:00:00")
    assert details[2] == datetime(2026, 10, 12, 10, tzinfo=UTC)


def test_occurrence_eligibility_checks_parent_dates_and_referenced_lifecycle() -> None:
    target_id = uuid4()
    item_id = uuid4()
    owner_id = uuid4()
    plan = PlanPayloadV1.model_validate(
        {
            "label": "Routine",
            "items": [
                {
                    "id": str(item_id),
                    "kind": "goal",
                    "label": "Move more",
                    "reference_id": str(target_id),
                }
            ],
        }
    )
    goal = GoalPayloadV1.model_validate(
        {"label": "Move more", "domain": "exercise", "start_date": "2026-10-05"}
    )
    parent_obj = SimpleNamespace(status="active", valid_from=None, valid_to=None)
    parent_resource = SimpleNamespace(
        resource_kind="plan", lifecycle="active", payload=plan.model_dump(mode="json")
    )
    identity = SimpleNamespace(parent_object_id=uuid4(), item_id=item_id, schedule_id=uuid4())
    link = SimpleNamespace(link_kind="plan_goal", target_object_id=target_id)
    target_obj = SimpleNamespace(status="active", valid_from=None, valid_to=None)
    target_resource = SimpleNamespace(
        resource_kind="goal", lifecycle="active", payload=goal.model_dump(mode="json")
    )
    links = {item_id: link}
    targets = {target_id: (target_obj, target_resource)}

    assert not _occurrence_is_eligible(
        SimpleNamespace(),
        owner_id,
        parent_obj,
        parent_resource,
        identity,
        date(2026, 10, 4),
        "UTC",
        links,
        targets,
    )
    assert _occurrence_is_eligible(
        SimpleNamespace(),
        owner_id,
        parent_obj,
        parent_resource,
        identity,
        date(2026, 10, 5),
        "UTC",
        links,
        targets,
    )
    target_resource.lifecycle = "paused"
    assert not _occurrence_is_eligible(
        SimpleNamespace(),
        owner_id,
        parent_obj,
        parent_resource,
        identity,
        date(2026, 10, 5),
        "UTC",
        links,
        targets,
    )


def test_planning_permissions_default_off_and_occurrence_links_are_typed() -> None:
    request = GoalCreateRequest.model_validate(
        {
            "id": str(uuid4()),
            "goal": {"label": "Move more", "domain": "exercise"},
        }
    )
    assert not request.ai_use_allowed
    assert not request.cross_domain_use_allowed

    linked = OccurrenceActionRequest.model_validate(
        {
            "expected_schedule_revision": 1,
            "expected_override_revision": None,
            "state": "completed",
            "linked_observation_id": str(uuid4()),
        }
    )
    assert linked.linked_observation_id is not None
    with pytest.raises(ValidationError):
        OccurrenceActionRequest.model_validate(
            {
                "expected_schedule_revision": 1,
                "expected_override_revision": None,
                "state": "completed",
                "linked_event_id": str(uuid4()),
                "linked_observation_id": str(uuid4()),
            }
        )


def test_huge_custom_number_and_quantity_are_rejected_without_overflow() -> None:
    definition = TrackerDefinitionV1.model_validate(
        {
            "name": "Weight note",
            "domain": "measurements",
            "fields": [
                {"id": "amount", "label": "Amount", "kind": "number", "required": True},
                {
                    "id": "quantity",
                    "label": "Quantity",
                    "kind": "quantity",
                    "unit": "dose",
                    "required": True,
                },
            ],
        }
    )

    with pytest.raises(ValueError, match="number value is invalid"):
        validate_tracker_values(
            definition,
            {"amount": 10**400, "quantity": {"value": 10**400, "unit": "dose"}},
        )


class _Rows:
    def __init__(self, rows: list[tuple[object, object | None]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, object | None]]:
        return self._rows


class _ReferenceSession:
    def __init__(self, rows: list[tuple[object, object | None]]) -> None:
        self.rows = rows

    def execute(self, _statement: object) -> _Rows:
        return _Rows(self.rows)


@pytest.mark.parametrize("order", [("regimen", "goal"), ("goal", "regimen")])
def test_repeated_target_does_not_erase_a_wrong_plan_edge(order: tuple[str, str]) -> None:
    target_id = uuid4()
    plan = PlanPayloadV1.model_validate(
        {
            "label": "Routine",
            "items": [
                {
                    "id": str(uuid4()),
                    "kind": item_kind,
                    "label": item_kind,
                    "reference_id": str(target_id),
                }
                for item_kind in order
            ],
        }
    )
    target = SimpleNamespace(id=target_id, status="active", object_type="goal")
    resource = SimpleNamespace(resource_kind="goal", lifecycle="active")

    with pytest.raises(PlanningValidationError, match="wrong resource type"):
        _validate_references(_ReferenceSession([(target, resource)]), uuid4(), "plan", plan)


def test_repeated_valid_plan_references_and_foreign_owner_references() -> None:
    target_id = uuid4()
    plan = PlanPayloadV1.model_validate(
        {
            "label": "Routine",
            "items": [
                {
                    "id": str(uuid4()),
                    "kind": "goal",
                    "label": f"Goal {index}",
                    "reference_id": str(target_id),
                }
                for index in range(2)
            ],
        }
    )
    target = SimpleNamespace(id=target_id, status="active", object_type="goal")
    resource = SimpleNamespace(resource_kind="goal", lifecycle="active")
    _validate_references(_ReferenceSession([(target, resource)]), uuid4(), "plan", plan)

    with pytest.raises(PlanningNotFound):
        _validate_references(_ReferenceSession([]), uuid4(), "plan", plan)
