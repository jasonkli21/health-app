from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_api.api.dependencies import get_current_owner, get_session, get_settings
from health_api.api.errors import APIError
from health_api.api.proposals import create_proposal, get_proposal, reject_proposal, router
from health_api.application import action_proposal_service as proposals
from health_api.application.errors import ActionProposalConflict, ActionProposalValidationError
from health_api.domain.planning import PlanPayloadV1
from health_api.domain.proposals import (
    PlanCreateDraft,
    ProfileCreateDraft,
    ProfileUpdateCommand,
    ProposalContent,
    ProposalCreateRequest,
    ProposalRejectRequest,
    ProposalState,
    StoredProposalContent,
)
from health_api.domain.schemas import ProfilePayloadV1
from health_api.main import create_app
from health_api.persistence.models import ActionCommandReceipt, ActionProposal, HealthObject, User


def _profile() -> ProfilePayloadV1:
    return ProfilePayloadV1.model_validate(
        {
            "kind": "fact",
            "category": "background",
            "key": "diet",
            "label": "Diet",
            "value": {"type": "text", "value": "vegetarian"},
        }
    )


def _proposal_state(command: ProfileUpdateCommand) -> ProposalState:
    now = datetime.now(UTC)
    return ProposalState(
        id=uuid4(),
        revision=1,
        content_hash="a" * 64,
        state="pending",
        origin="user",
        rationale="",
        evidence_refs=[],
        commands=[command],
        created_at=now,
        expires_at=now + timedelta(hours=1),
        updated_at=now,
    )


def test_profile_update_response_preserves_omission_and_explicit_null() -> None:
    target = uuid4()
    omitted = ProfileUpdateCommand(
        action="profile.update",
        object_id=target,
        expected_revision=1,
        profile=_profile(),
    )
    explicit_clear = ProfileUpdateCommand(
        action="profile.update",
        object_id=target,
        expected_revision=1,
        profile=_profile(),
        notes=None,
        metadata=None,
        valid_from=None,
        valid_to=None,
    )

    omitted_json = _proposal_state(omitted).model_dump(mode="json", exclude_unset=True)
    cleared_json = _proposal_state(explicit_clear).model_dump(mode="json", exclude_unset=True)
    omitted_command = omitted_json["commands"][0]
    cleared_command = cleared_json["commands"][0]

    assert "notes" not in omitted_command
    assert "metadata" not in omitted_command
    assert "valid_from" not in omitted_command
    assert cleared_command["notes"] is None
    assert cleared_command["metadata"] is None
    assert cleared_command["valid_from"] is None
    assert cleared_command["valid_to"] is None


def test_http_proposal_response_preserves_omission_and_explicit_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid4()
    target_a, target_b = uuid4(), uuid4()
    omitted = ProfileUpdateCommand(
        action="profile.update",
        object_id=target_a,
        expected_revision=1,
        profile=_profile(),
    )
    explicit_clear = ProfileUpdateCommand(
        action="profile.update",
        object_id=target_b,
        expected_revision=1,
        profile=_profile(),
        notes=None,
        metadata=None,
        valid_from=None,
        valid_to=None,
    )
    now = datetime.now(UTC)
    proposal_id = uuid4()
    state = ProposalState(
        id=proposal_id,
        revision=1,
        content_hash="e" * 64,
        state="pending",
        origin="user",
        rationale="",
        evidence_refs=[],
        commands=[omitted, explicit_clear],
        created_at=now,
        expires_at=now + timedelta(hours=1),
        updated_at=now,
    )
    monkeypatch.setattr(
        "health_api.api.proposals.create_action_proposal", lambda *_args, **_kwargs: (state, True)
    )
    app = create_app()
    app.dependency_overrides[get_current_owner] = lambda: owner_id
    app.dependency_overrides[get_session] = lambda: MagicMock()
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        action_proposal_generation_enabled=True,
        action_proposal_ttl_hours=24,
    )
    request_body = {
        "id": str(proposal_id),
        "commands": [
            {
                "action": "profile.update",
                "object_id": str(target_a),
                "expected_revision": 1,
                "profile": _profile().model_dump(mode="json"),
            },
            {
                "action": "profile.update",
                "object_id": str(target_b),
                "expected_revision": 1,
                "profile": _profile().model_dump(mode="json"),
                "notes": None,
                "metadata": None,
                "valid_from": None,
                "valid_to": None,
            },
        ],
    }

    with TestClient(app) as client:
        response = client.post("/action-proposals", json=request_body)

    assert response.status_code == 201
    omitted_response, cleared_response = response.json()["commands"]
    assert "notes" not in omitted_response
    assert "metadata" not in omitted_response
    assert "valid_from" not in omitted_response
    assert cleared_response["notes"] is None
    assert cleared_response["metadata"] is None
    assert cleared_response["valid_from"] is None
    assert cleared_response["valid_to"] is None


def test_proposal_routes_exclude_unset_recursively_for_command_roundtrips() -> None:
    response_routes = [
        route
        for route in router.routes
        if isinstance(route, APIRoute)
        and route.path
        in {
            "/action-proposals",
            "/action-proposals/{proposal_id}",
            "/action-proposals/{proposal_id}/apply",
            "/action-proposals/{proposal_id}/reject",
        }
    ]
    assert response_routes
    assert all(route.response_model_exclude_unset for route in response_routes)


def test_ai_originated_proposal_creation_fails_closed_before_storage() -> None:
    with pytest.raises(ActionProposalValidationError, match="AI-originated proposals are disabled"):
        proposals.create_action_proposal(
            MagicMock(),
            uuid4(),
            uuid4(),
            None,
            24,
            origin_kind="ai",  # type: ignore[arg-type]
        )


def test_proposal_generation_switch_blocks_create_without_blocking_read_or_reject_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "health_api.api.proposals.create_action_proposal",
        MagicMock(side_effect=AssertionError("generation must be denied before storage")),
    )
    settings = SimpleNamespace(action_proposal_generation_enabled=False)
    with pytest.raises(APIError) as error:
        create_proposal(None, None, uuid4(), MagicMock(), settings)  # type: ignore[arg-type]
    assert error.value.status_code == 503
    assert error.value.code == "proposal_generation_disabled"
    monkeypatch.setattr("health_api.api.proposals.get_action_proposal", lambda *_: "readable")
    monkeypatch.setattr("health_api.api.proposals.reject_action_proposal", lambda *_: "rejected")
    assert get_proposal(uuid4(), uuid4(), MagicMock()) == "readable"  # type: ignore[arg-type]
    assert (
        reject_proposal(uuid4(), ProposalRejectRequest(proposal_revision=1), uuid4(), MagicMock())
        == "rejected"
    )


def test_enabled_generation_uses_server_ttl_and_owner_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id, proposal_id = uuid4(), uuid4()
    body = ProposalCreateRequest(
        id=proposal_id,
        commands=[ProfileCreateDraft(action="profile.create", profile=_profile())],
    )
    response = MagicMock()
    settings = SimpleNamespace(
        action_proposal_generation_enabled=True, action_proposal_ttl_hours=18
    )
    session = MagicMock()
    created_state = _proposal_state(
        ProfileUpdateCommand(
            action="profile.update",
            object_id=uuid4(),
            expected_revision=1,
            profile=_profile(),
        )
    )
    create = MagicMock(return_value=(created_state, True))
    monkeypatch.setattr("health_api.api.proposals.create_action_proposal", create)

    assert create_proposal(body, response, owner_id, session, settings) == created_state  # type: ignore[arg-type]
    create.assert_called_once_with(
        session,
        owner_id,
        proposal_id,
        body,
        18,
        origin_kind="user",
        origin_metadata={"source": "owner-authored"},
    )
    assert response.status_code == 201


def test_prior_receipt_replay_compares_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    owner_id, proposal_id = uuid4(), uuid4()
    owner = SimpleNamespace(id=owner_id, lifecycle="active")
    receipt = SimpleNamespace(proposal_id=proposal_id, proposal_revision=2, content_hash="b" * 64)
    session = MagicMock()
    session.begin.return_value.__enter__ = MagicMock(return_value=None)
    session.begin.return_value.__exit__ = MagicMock(return_value=None)
    session.scalar.return_value = owner
    monkeypatch.setattr(proposals, "_find_receipt", lambda *_: receipt)

    with pytest.raises(ActionProposalConflict, match="idempotency key"):
        proposals.apply_action_proposal(
            session, owner_id, proposal_id, 999, "b" * 64, "existing-key"
        )


def test_applied_proposal_binds_a_successful_alternate_key_to_canonical_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id, proposal_id = uuid4(), uuid4()
    result_json = [{"object_id": str(uuid4()), "object_type": "goal", "revision": 1}]
    owner = SimpleNamespace(id=owner_id, lifecycle="active")
    proposal = SimpleNamespace(
        id=proposal_id,
        owner_id=owner_id,
        state="applied",
        applied_revision=2,
    )
    original = SimpleNamespace(content_hash="c" * 64, result_json=result_json)
    session = MagicMock()
    session.begin.return_value.__enter__ = MagicMock(return_value=None)
    session.begin.return_value.__exit__ = MagicMock(return_value=None)
    session.scalar.side_effect = [owner, proposal, original]
    monkeypatch.setattr(proposals, "_find_receipt", lambda *_: None)
    monkeypatch.setattr(proposals, "_state_from_row", lambda *_: "canonical-state")

    outcome = proposals.apply_action_proposal(
        session, owner_id, proposal_id, 2, "c" * 64, "alternate-key"
    )

    assert outcome.replayed is True
    receipt = session.add.call_args.args[0]
    assert isinstance(receipt, ActionCommandReceipt)
    assert receipt.idempotency_key == "alternate-key"
    assert receipt.proposal_revision == 2
    assert receipt.result_json == result_json


def test_archived_profile_update_fails_draft_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    owner_id, target_id = uuid4(), uuid4()
    command = ProfileUpdateCommand(
        action="profile.update",
        object_id=target_id,
        expected_revision=1,
        profile=_profile(),
    )
    snapshot = {
        "rationale": "",
        "evidence_refs": [],
        "commands": [command.model_dump(mode="json", exclude_unset=True)],
    }
    monkeypatch.setattr(
        proposals,
        "get_profile_item",
        lambda *_: (SimpleNamespace(status="archived", revision=1), None, None),
    )

    with pytest.raises(ActionProposalValidationError, match="Profile target is archived"):
        proposals._validate_commands(MagicMock(), owner_id, snapshot)


def test_changed_evidence_hint_contains_owner_current_revision_and_snapshot() -> None:
    owner_id, object_id = uuid4(), uuid4()
    content = StoredProposalContent.model_validate(
        {
            "rationale": "",
            "evidence_refs": [{"object_id": str(object_id), "revision": 2}],
            "commands": [
                {
                    "action": "profile.create",
                    "id": str(uuid4()),
                    "profile": _profile().model_dump(mode="json"),
                }
            ],
        }
    )
    current = SimpleNamespace(id=object_id, revision=3, status="active", title="Current title")
    snapshot = {"object_type": "event", "title": "Current title", "revision": 3}
    session = MagicMock()
    session.scalars.side_effect = [
        [current],
        [SimpleNamespace(object_id=object_id, revision=3, snapshot=snapshot)],
    ]

    hints = proposals._changed_reference_hints(session, owner_id, content)

    assert hints == [
        {
            "object_id": str(object_id),
            "reference_kind": "evidence",
            "expected_revision": 2,
            "current_revision": 3,
            "current_status": "active",
            "current_title": "Current title",
            "current_snapshot": snapshot,
        }
    ]


def test_plan_reference_revisions_are_captured_in_hashed_proposal_content() -> None:
    owner_id, proposal_id, goal_id, item_id = uuid4(), uuid4(), uuid4(), uuid4()
    content = ProposalContent(
        commands=[
            PlanCreateDraft(
                action="plan.create",
                plan=PlanPayloadV1.model_validate(
                    {
                        "label": "Plan",
                        "items": [
                            {
                                "id": str(item_id),
                                "kind": "goal",
                                "label": "Goal",
                                "reference_id": str(goal_id),
                            }
                        ],
                    }
                ),
            )
        ]
    )
    session = MagicMock()
    session.scalars.side_effect = [
        [SimpleNamespace(id=goal_id, revision=4)],
        [SimpleNamespace(id=goal_id, revision=5)],
    ]

    first = proposals._draft_snapshot(content, proposal_id, session, owner_id)
    second = proposals._draft_snapshot(content, proposal_id, session, owner_id)

    first_reference = first["commands"][0]["reference_revisions"][0]
    second_reference = second["commands"][0]["reference_revisions"][0]
    assert first_reference == {"object_id": str(goal_id), "revision": 4}
    assert second_reference == {"object_id": str(goal_id), "revision": 5}
    assert proposals._content_hash(first) != proposals._content_hash(second)


def test_changed_reference_snapshot_preview_is_bounded() -> None:
    review = proposals._bounded_review_snapshot(
        {"object_type": "event", "title": "Long", "payload": {"notes": "x" * 20_000}}
    )

    assert review["truncated"] is True
    assert len(proposals._json_canonical(review).encode("utf-8")) < 4096


def test_list_summary_uses_a_bounded_revision_query_and_omits_command_payloads() -> None:
    owner_id = uuid4()
    proposal = SimpleNamespace(
        id=uuid4(),
        current_revision=1,
        content_hash="d" * 64,
        state="pending",
        origin_kind="user",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        updated_at=datetime.now(UTC),
    )
    revision = SimpleNamespace(
        proposal_id=proposal.id,
        revision=1,
        content_hash="d" * 64,
        snapshot={
            "rationale": "summary only",
            "evidence_refs": [],
            "commands": [
                {
                    "action": "profile.create",
                    "id": str(uuid4()),
                    "profile": _profile().model_dump(mode="json"),
                }
            ],
        },
    )
    session = MagicMock()
    session.scalars.return_value = [revision]

    summaries = proposals.action_proposal_summaries(session, owner_id, [proposal])

    assert len(summaries) == 1
    assert summaries[0].rationale == "summary only"
    assert not hasattr(summaries[0], "commands")
    session.scalars.assert_called_once()


def test_database_apply_failure_after_target_write_rolls_back_proposal_effects(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id, proposal_id = uuid4(), uuid4()
    db_session.add(User(id=owner_id, display_timezone="UTC", lifecycle="active", daily_sequence=0))
    db_session.commit()
    state, created = proposals.create_action_proposal(
        db_session,
        owner_id,
        proposal_id,
        ProposalContent(commands=[ProfileCreateDraft(action="profile.create", profile=_profile())]),
        24,
    )
    assert created is True

    target_results = proposals._target_results

    def fail_after_target_write(*args: Any, **kwargs: Any) -> list[Any]:
        target_results(*args, **kwargs)
        raise RuntimeError("injected failure after target write")

    monkeypatch.setattr(proposals, "_target_results", fail_after_target_write)
    with pytest.raises(RuntimeError, match="injected failure"):
        proposals.apply_action_proposal(
            db_session, owner_id, proposal_id, state.revision, state.content_hash, "rollback-key"
        )

    db_session.rollback()
    assert (
        db_session.scalar(select(HealthObject.id).where(HealthObject.owner_id == owner_id)) is None
    )
    assert (
        db_session.scalar(
            select(ActionCommandReceipt.id).where(ActionCommandReceipt.owner_id == owner_id)
        )
        is None
    )
    stored = db_session.get(ActionProposal, proposal_id)
    assert stored is not None and stored.state == "pending"


def test_database_proposal_detail_is_owner_scoped(db_session: Session) -> None:
    owner_id, foreign_owner_id, proposal_id = uuid4(), uuid4(), uuid4()
    db_session.add_all(
        [
            User(id=owner_id, display_timezone="UTC", lifecycle="active", daily_sequence=0),
            User(id=foreign_owner_id, display_timezone="UTC", lifecycle="active", daily_sequence=0),
        ]
    )
    db_session.commit()
    proposals.create_action_proposal(
        db_session,
        owner_id,
        proposal_id,
        ProposalContent(commands=[ProfileCreateDraft(action="profile.create", profile=_profile())]),
        24,
    )
    db_session.rollback()

    from health_api.application.errors import ActionProposalNotFound

    with pytest.raises(ActionProposalNotFound):
        proposals.get_action_proposal(db_session, foreign_owner_id, proposal_id)
