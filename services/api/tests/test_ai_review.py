from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from health_api.api.ai import (
    _decode_cursor,
    _invoke_adapter,
    _owner_binding,
    _query_binding,
    _validate_adapter_response,
)
from health_api.api.errors import APIError
from health_api.application.ai_context_service import (
    _eligible_candidates,
    _payload_search_projection,
)
from health_api.domain.ai import AIContextRequest, AssistantMessageRequest
from health_api.persistence.models import PlanningResource

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


def test_adapter_response_is_bound_to_health_request_and_counts() -> None:
    request_id = UUID("00000000-0000-0000-0000-000000000456")
    object_id = UUID("00000000-0000-0000-0000-000000000123")
    result = _validate_adapter_response(
        {
            "request_id": str(request_id),
            "reply": "Review your sleep log.",
            "risk_class": "general_wellness",
            "context_summary": {"invented": 999},
            "evidence_refs": [{"object_id": str(object_id), "revision": 2}],
            "service_status": "complete",
        },
        request_id=request_id,
        included_counts={"event": 1},
        permitted_refs={(object_id, 2): ("event", "Sleep log")},
        requested_risk="consequential_medical",
    )
    assert result.context_summary == {"event": 1}
    assert result.risk_class == "consequential_medical"


def test_adapter_response_rejects_mismatched_ids_and_invented_evidence() -> None:
    request_id = UUID("00000000-0000-0000-0000-000000000456")
    response = {
        "request_id": str(request_id),
        "reply": "Unsupported.",
        "risk_class": "general_wellness",
        "context_summary": {},
        "evidence_refs": [],
        "service_status": "complete",
    }
    with pytest.raises(APIError) as mismatched:
        _validate_adapter_response(
            {**response, "request_id": str(OWNER)},
            request_id=request_id,
            included_counts={},
            permitted_refs={},
            requested_risk="general_wellness",
        )
    assert mismatched.value.code == "assistant_invalid_response"
    with pytest.raises(APIError) as unsupported_evidence:
        _validate_adapter_response(
            {
                **response,
                "evidence_refs": [{"object_id": str(OWNER), "revision": 1}],
            },
            request_id=request_id,
            included_counts={},
            permitted_refs={},
            requested_risk="general_wellness",
        )
    assert unsupported_evidence.value.code == "assistant_invalid_evidence"


@pytest.mark.asyncio
async def test_adapter_deadline_cancels_a_never_finishing_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import health_api.api.ai as ai_routes

    class NeverFinishes:
        async def send_message(self, _request: object, _context: object) -> object:
            await asyncio.Event().wait()

    monkeypatch.setattr(ai_routes, "ADAPTER_TIMEOUT_SECONDS", 0.001)
    request = AssistantMessageRequest(
        message="test", scope=AIContextRequest(task="test", resource_types=["event"])
    )
    with pytest.raises(APIError) as timeout:
        await _invoke_adapter(NeverFinishes(), request, None)  # type: ignore[arg-type]
    assert timeout.value.code == "assistant_unavailable"
    assert timeout.value.message == "Assistant request timed out."


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
