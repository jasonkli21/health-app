from __future__ import annotations

import base64
import json
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from health_api.api.ai import (
    _decode_cursor,
    _owner_binding,
    _query_binding,
)
from health_api.api.errors import APIError
from health_api.application.ai_context_admission import _eligibility_conditions
from health_api.application.ai_context_pack import _append_budgeted_entries
from health_api.application.ai_context_projection import (
    _context_entry,
    _filter_relationships_to_included_entries,
)
from health_api.application.ai_context_service import (
    _eligible_candidates,
    _payload_search_projection,
)
from health_api.domain.ai import AIContextEntry, AIContextPack, AIContextRequest
from health_api.integrations.personal_ai import create_personal_ai_adapter
from health_api.persistence.models import EventItem, ObservationItem, PlanningResource
from sqlalchemy import and_, select
from sqlalchemy.dialects import postgresql

OWNER = UUID("00000000-0000-0000-0000-000000000101")


def _cursor(payload: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


@pytest.mark.parametrize(
    "payload",
    [
        3,
        [],
        {"v": 1, "owner": "x", "query": "x", "types": [], "recorded_at": "x", "id": 123},
    ],
)
def test_cursor_rejects_well_formed_json_with_wrong_shapes(payload: object) -> None:
    with pytest.raises(APIError) as error:
        _decode_cursor(_cursor(payload), OWNER, "sleep", ("event",))
    assert error.value.code == "invalid_cursor"


def test_cursor_binds_owner_query_and_types() -> None:
    payload = {
        "v": 1,
        "owner": _owner_binding(OWNER),
        "query": _query_binding("sleep"),
        "types": ["event"],
        "recorded_at": "2026-10-05T12:00:00+00:00",
        "id": "00000000-0000-0000-0000-000000000123",
    }
    result = _decode_cursor(_cursor(payload), OWNER, "sleep", ("event",))
    assert result == (datetime(2026, 10, 5, 12, tzinfo=UTC), UUID(payload["id"]))


def test_context_request_supports_bounded_domain_and_item_narrowing() -> None:
    request = AIContextRequest(
        task="Review recent sleep",
        resource_types=["event", "observation"],
        domains=["sleep"],
        excluded_object_ids=[UUID("00000000-0000-0000-0000-000000000123")],
    )
    assert request.domains == ["sleep"]
    assert len(request.excluded_object_ids) == 1


def test_personal_ai_factory_exposes_disabled_status_without_transport() -> None:
    integration = create_personal_ai_adapter()

    assert integration.configured is False
    assert integration.status == "disabled"
    assert integration.reason.endswith("implemented and reviewed.")
    assert not hasattr(integration, "send_message")


def test_search_projection_removes_relationship_fields_and_planning_dates_compile() -> None:
    projected = _payload_search_projection(PlanningResource.payload)
    compiled_projection = projected.compile(dialect=postgresql.dialect())
    assert {"related", "items", "linked_observation_ids"}.issubset(
        set(compiled_projection.params.values())
    )
    candidates = _eligible_candidates(
        OWNER,
        resource_types=("context", "regimen", "plan", "goal"),
        task="sleep",
        as_of=datetime(2026, 10, 5, 12, tzinfo=UTC),
        timezone="America/Los_Angeles",
        lookback_days=30,
        search_text="sleep",
    )
    compiled = candidates.select().compile(dialect=postgresql.dialect())
    assert {"start_at", "end_at", "start_date", "end_date"}.issubset(set(compiled.params.values()))


def test_candidate_admission_requires_owner_consent_currentness_time_and_narrowing() -> None:
    excluded_id = uuid4()
    conditions = _eligibility_conditions(
        OWNER,
        object_type="event",
        payload=EventItem.payload,
        as_of=datetime(2026, 10, 8, 12, tzinfo=UTC),
        start_date=date(2026, 10, 1),
        start_at=datetime(2026, 10, 1, tzinfo=UTC),
        end_date=date(2026, 10, 8),
        excluded_object_ids=(excluded_id,),
        domains=("sleep",),
    )
    compiled = select(1).where(and_(*conditions)).compile(dialect=postgresql.dialect())
    sql = compiled.string

    assert "health_objects.owner_id" in sql
    assert "health_objects.status" in sql
    assert "health_objects.ai_use_allowed IS true" in sql
    assert "health_objects.valid_from" in sql and "health_objects.valid_to" in sql
    assert "health_objects.domain IN" in sql
    assert "health_objects.id NOT IN" in sql
    assert excluded_id in compiled.params["id_1"]
    assert compiled.params["domain_1"] == ["sleep"]


def test_custom_tracker_values_do_not_pass_the_context_admission_gate() -> None:
    conditions = _eligibility_conditions(
        OWNER,
        object_type="observation",
        payload=ObservationItem.payload,
        as_of=datetime(2026, 10, 8, 12, tzinfo=UTC),
        start_date=date(2026, 10, 1),
        start_at=datetime(2026, 10, 1, tzinfo=UTC),
        end_date=date(2026, 10, 8),
    )
    compiled = select(1).where(and_(*conditions)).compile(dialect=postgresql.dialect())

    assert "observations.payload" in compiled.string
    assert "custom" in compiled.params.values()


def _entry(
    object_id: UUID,
    object_type: str,
    payload: dict[str, object],
) -> AIContextEntry:
    return AIContextEntry(
        object_id=object_id,
        revision=1,
        object_type=object_type,  # type: ignore[arg-type]
        domain="planning" if object_type in {"context", "plan"} else "nutrition",
        title="Review-test entry",
        valid_from=None,
        valid_to=None,
        source_kind="manual",
        confirmation_status="user_confirmed",
        content={"payload": payload, "notes": None},
        content_is_user_data=True,
        relevance_reason="Current entry",
    )


def test_projection_drops_relationships_to_ineligible_endpoints() -> None:
    hidden_id, included_id = uuid4(), uuid4()
    context = _entry(
        uuid4(),
        "context",
        {
            "related": [
                {"object_id": str(hidden_id), "label": "private endpoint"},
                {"object_id": str(included_id), "label": "included endpoint"},
            ]
        },
    )
    included = _entry(included_id, "event", {"kind": "meal"})

    _filter_relationships_to_included_entries([context, included])

    related = context.content["payload"]["related"]
    assert related == [{"object_id": str(included_id), "label": "included endpoint"}]
    assert str(hidden_id) not in context.model_dump_json()


def test_projection_preserves_date_only_time_and_unknown_values() -> None:
    local_date = date(2026, 10, 8)
    row = SimpleNamespace(
        object_type="event",
        priority=4,
        object_id=uuid4(),
        revision=2,
        domain="measurements",
        title="Review-test measurement",
        valid_from=None,
        valid_to=None,
        source_kind="manual",
        confirmation_status="user_confirmed",
        payload={"value": None, "known": False, "zero": 0},
        notes=None,
        health_metadata={},
        time_precision="date_only",
        timezone="Pacific/Auckland",
        local_date=local_date,
        occurred_at=None,
        ended_at=None,
    )

    entry = _context_entry(row)

    assert entry.content["time"] == {
        "precision": "date_only",
        "timezone": "Pacific/Auckland",
        "local_date": "2026-10-08",
    }
    assert entry.content["payload"] == {"value": None, "known": False, "zero": 0}

    instant = datetime(2026, 10, 8, 19, 30, tzinfo=UTC)
    instant_row = SimpleNamespace(
        **{
            **row.__dict__,
            "time_precision": "instant",
            "timezone": "UTC",
            "local_date": None,
            "occurred_at": instant,
            "ended_at": None,
        }
    )
    instant_entry = _context_entry(instant_row)
    assert instant_entry.content["time"] == {
        "precision": "instant",
        "timezone": "UTC",
        "occurred_at": instant.isoformat(),
        "ended_at": None,
    }


def _empty_pack(now: datetime) -> AIContextPack:
    return AIContextPack(
        schema_version=1,
        request_id=UUID("00000000-0000-0000-0000-000000000123"),
        owner_scope="a" * 32,
        built_at=now,
        as_of=now,
        timezone="UTC",
        task="Review-test budget",
        task_kind="general_wellness",
        resource_types=["event"],
        domains=[],
        sections=["entries"],
        lookback_days=30,
        entries=[],
        today_summary_date=now.date(),
        today_summary_scope="included_opted_in_entries_only",
        today_summaries=[],
        included_counts={},
        omitted_by_user=0,
        omitted_by_budget=0,
        truncated=False,
        budget_bytes=65_536,
        serialized_bytes=0,
    )


def test_one_oversized_candidate_is_deterministically_omitted() -> None:
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    row = SimpleNamespace(
        object_type="event",
        priority=4,
        object_id=UUID("00000000-0000-0000-0000-000000000456"),
        revision=1,
        domain="nutrition",
        title="Review-test oversized entry",
        valid_from=None,
        valid_to=None,
        source_kind="manual",
        confirmation_status="user_confirmed",
        payload={"large": "x" * 70_000},
        notes=None,
        health_metadata={},
        time_precision=None,
        timezone=None,
        local_date=None,
        occurred_at=None,
        ended_at=None,
    )
    first = _empty_pack(now)
    second = _empty_pack(now)

    assert _append_budgeted_entries(first, [row]) is False
    assert _append_budgeted_entries(second, [row]) is False

    assert first.entries == second.entries == []
    assert first.omitted_by_budget == second.omitted_by_budget == 1
    assert first.truncated is second.truncated is True
    assert first.serialized_bytes == second.serialized_bytes <= 65_536
