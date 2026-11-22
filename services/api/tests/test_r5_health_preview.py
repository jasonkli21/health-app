from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from health_api.application.account_data_service import (
    begin_owner_deletion,
    export_owner_snapshot,
    process_owner_deletion,
)
from health_api.application.profile_service import (
    CreateProfile,
    archive_profile_item,
    create_profile_item,
    update_profile_item,
)
from health_api.application.r5_health_caller import (
    R5CallerTarget,
    R5OriginalKeys,
    reserve_r5_operation_keys,
)
from health_api.application.r5_health_source import (
    R5HealthSelection,
    R5PreviewUnavailable,
    R5SourceAuthority,
    parse_r5_source_request,
    read_r5_health_preference,
)
from health_api.config.settings import Settings
from health_api.domain.schemas import ProfilePayloadV1, ProfileValidity
from health_api.integrations.firebase_auth import VerifiedIdentity
from health_api.integrations.object_storage import LocalObjectStorage
from health_api.persistence.models import ProviderIdentity, R5PreviewReservation, User

ISSUER = "https://securetoken.google.com/health-test"
BODY = {
    "schema_version": "health-context-read-v1",
    "application_id": "health",
    "workspace_id": None,
    "purpose": "personal_ai_context",
    "operation": "profile",
    "category": "profile_preferences",
    "fields": ["record"],
    "max_results": 1,
}
PROFILE = {
    "kind": "preference",
    "category": "preferences",
    "key": "r5_synthetic_presentation_format",
    "label": "Synthetic presentation format",
    "value": {"type": "text", "value": "bullets"},
}
CREATE_DIGEST = hashlib.sha256(b"synthetic create fixture").hexdigest()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="test",
        auth_mode="firebase",
        firebase_project_id="health-test",
        personal_ai_context_service_audience="https://health.test",
        personal_ai_context_service_account="pas@health.test",
        personal_ai_context_read_enabled=True,
        personal_ai_r5_preview_enabled=True,
    )


def make_authority(
    selection: R5HealthSelection | None = None,
    *,
    subject: str = "synthetic-uid",
    auth_time: int | None = None,
) -> R5SourceAuthority:
    now = int(datetime.now(UTC).timestamp())
    return R5SourceAuthority(
        VerifiedIdentity(ISSUER, subject, now if auth_time is None else auth_time, now),
        uuid4(),
        1,
        uuid4(),
        selection or R5HealthSelection(uuid4(), 1),
    )


def wire(selection: R5HealthSelection, **changes: object) -> bytes:
    return json.dumps(
        {
            **BODY,
            "entity_refs": [{"object_type": "profile_item", "object_id": str(selection.object_id)}],
            **changes,
        }
    ).encode()


def test_r5_gate_defaults_off_before_access(settings: Settings) -> None:
    assert not Settings().personal_ai_r5_preview_enabled
    assert not settings.personal_ai_federation_export_enabled
    with pytest.raises(ValueError, match="personal_ai_r5_preview_requires_offline_test_context"):
        Settings(personal_ai_r5_preview_enabled=True)
    with pytest.raises(ValueError, match="personal_ai_r5_preview_requires_offline_test_context"):
        Settings.model_validate(settings.model_dump() | {"app_env": "local"})

    authority = make_authority()
    reauthorize = Mock()
    sessions = Mock()
    with pytest.raises(R5PreviewUnavailable):
        read_r5_health_preference(
            sessions, Settings(), wire(authority.selection), authority, reauthorize
        )
    reauthorize.assert_not_called()
    sessions.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": "health-context-read-v2"},
        {"workspace_id": "workspace"},
        {"purpose": "health_dietary_restrictions_to_travel"},
        {"application_id": "travel"},
        {"fields": ["record", "notes"]},
        {"fields": ["healthkit"]},
        {"entity_refs": []},
        {"max_results": 2},
        {"max_bytes": 1_000_000},
        {"operation": "catalog"},
        {"category": "profile_constraints"},
        {"owner_id": str(uuid4())},
    ],
)
def test_r5_rejects_scope_before_authority_or_db(settings: Settings, changes: dict) -> None:
    authority = make_authority()
    reauthorize = Mock()
    sessions = Mock()
    with pytest.raises(R5PreviewUnavailable):
        read_r5_health_preference(
            sessions, settings, wire(authority.selection, **changes), authority, reauthorize
        )
    reauthorize.assert_not_called()
    sessions.assert_not_called()


def test_r5_rejects_duplicate_missing_invalid_and_oversized_scope() -> None:
    authority = make_authority()
    good = wire(authority.selection)
    assert parse_r5_source_request(good, authority.selection).fields == ("record",)
    for body in (
        good.replace(b"null", b'null, "workspace_id": null'),
        good.replace(b'"workspace_id": null, ', b""),
        good + b" " * 32_768,
        b" ",
    ):
        with pytest.raises(R5PreviewUnavailable):
            parse_r5_source_request(body, authority.selection)


def test_r5_rejects_wrong_live_binding_with_zero_protected_reads(settings: Settings) -> None:
    authority = make_authority()
    now = int(datetime.now(UTC).timestamp())
    sessions = Mock()
    for current in (
        None,
        replace(authority, identity=VerifiedIdentity(ISSUER, "different-uid", now, now)),
        replace(
            authority, identity=VerifiedIdentity("https://wrong.test", "synthetic-uid", now, now)
        ),
        replace(authority, identity=VerifiedIdentity(ISSUER, "synthetic-uid", now - 360, now)),
        replace(authority, enrollment_generation=2),
        replace(authority, installation_id=uuid4()),
        replace(authority, selection=R5HealthSelection(uuid4(), 1)),
    ):
        with pytest.raises(R5PreviewUnavailable):
            read_r5_health_preference(
                sessions,
                settings,
                wire(authority.selection),
                authority,
                lambda current=current: current,
            )
    sessions.assert_not_called()


def seed_owner(session: Session, uid: str) -> UUID:
    owner = User(id=uuid4(), display_timezone="UTC")
    session.add(owner)
    session.flush()
    session.add(ProviderIdentity(issuer=ISSUER, subject=uid, user_id=owner.id))
    return owner.id


def seed_profile(
    session: Session,
    owner: UUID,
    *,
    ai: bool = True,
    cross: bool = True,
    valid_to: datetime | None = None,
    **changes: object,
) -> R5HealthSelection:
    created = create_profile_item(
        session,
        owner,
        CreateProfile(
            id=uuid4(),
            profile=ProfilePayloadV1.model_validate(PROFILE | changes),
            ai_use_allowed=ai,
            cross_domain_use_allowed=cross,
            validity=ProfileValidity(valid_to=valid_to),
            notes="synthetic notes outside the field grant",
        ),
    ).aggregate[0]
    return R5HealthSelection(created.id, created.revision)


def test_r5_native_exact_scope_consent_regrant_and_interrupted_authority(
    db_session: Session, postgres_engine: Engine, settings: Settings
) -> None:
    a = seed_owner(db_session, "synthetic-a")
    b = seed_owner(db_session, "synthetic-b")
    a1 = seed_profile(db_session, a)
    a2 = seed_profile(db_session, a)
    b1 = seed_profile(db_session, b)
    b2 = seed_profile(db_session, b)
    ai_denied = seed_profile(db_session, a, ai=False)
    cross_denied = seed_profile(db_session, a, cross=False)
    expired = seed_profile(db_session, a, valid_to=datetime.now(UTC) - timedelta(days=1))
    arbitrary_nested_value = seed_profile(
        db_session, a, value={"type": "text_list", "value": ["other synthetic value"]}
    )
    db_session.commit()
    sessions = sessionmaker(bind=postgres_engine, expire_on_commit=False)

    def read(subject: str, selection: R5HealthSelection):
        authority = make_authority(selection, subject=subject)
        return read_r5_health_preference(
            sessions, settings, wire(selection), authority, lambda: authority
        )

    for owner, uid, selection in (
        (b, "synthetic-b", b2),
        (a, "synthetic-a", a2),
        (a, "synthetic-a", a1),
        (b, "synthetic-b", b1),
    ):
        resolved, response = read(uid, selection)
        assert resolved == owner
        assert len(response.items) == 1
        item = response.items[0]
        assert item.object_id == selection.object_id
        assert item.payload.record == PROFILE
        assert item.payload.notes is None
        assert item.permission_dependencies[0].version.endswith(":r1:ai1:cross1")

    for denied in (
        b1,
        ai_denied,
        cross_denied,
        expired,
        arbitrary_nested_value,
        replace(a1, revision=2),
        R5HealthSelection(uuid4(), 1),
    ):
        with pytest.raises(R5PreviewUnavailable):
            read("synthetic-a", denied)

    authority = make_authority(a1, subject="synthetic-a")
    with pytest.raises(R5PreviewUnavailable):
        read_r5_health_preference(sessions, settings, wire(a2), authority, lambda: authority)
    with pytest.raises(R5PreviewUnavailable):
        read_r5_health_preference(
            sessions, settings, wire(a1, max_bytes=512), authority, lambda: authority
        )
    live: Iterator[R5SourceAuthority | None] = iter((authority, None))
    with pytest.raises(R5PreviewUnavailable):
        read_r5_health_preference(sessions, settings, wire(a1), authority, lambda: next(live))

    checked = 0

    def revoke_between_projection_and_verify() -> R5SourceAuthority:
        nonlocal checked
        checked += 1
        if checked == 2:
            update_profile_item(db_session, a, a1.object_id, 1, {"cross_domain_use_allowed": False})
            db_session.commit()
        return authority

    with pytest.raises(R5PreviewUnavailable):
        read_r5_health_preference(
            sessions, settings, wire(a1), authority, revoke_between_projection_and_verify
        )
    updated = update_profile_item(
        db_session, a, a1.object_id, 2, {"cross_domain_use_allowed": True}
    )[0]
    db_session.commit()
    with pytest.raises(R5PreviewUnavailable):
        read("synthetic-a", a1)
    current = replace(a1, revision=updated.revision)
    _, response = read("synthetic-a", current)
    assert response.items[0].permission_dependencies[0].version.endswith(":r3:ai1:cross1")

    archive_profile_item(db_session, a, current.object_id, current.revision)
    db_session.commit()
    with pytest.raises(R5PreviewUnavailable):
        read("synthetic-a", current)


def test_r5_native_reservations_retry_isolation_immutability_export_erasure(
    db_session: Session, postgres_engine: Engine, settings: Settings, tmp_path: Path
) -> None:
    a = seed_owner(db_session, "synthetic-a")
    b = seed_owner(db_session, "synthetic-b")
    a1 = seed_profile(db_session, a)
    a2 = seed_profile(db_session, a)
    b1 = seed_profile(db_session, b)
    db_session.commit()
    sessions = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    intent = uuid4()
    target = R5CallerTarget(
        uuid4(), uuid4(), uuid4(), hashlib.sha256(b"test recipient").hexdigest()
    )
    authority = make_authority(a1, subject="synthetic-a")

    def reserve(
        selected: R5SourceAuthority = authority,
        key: UUID = intent,
        destination: R5CallerTarget = target,
        digest: str = CREATE_DIGEST,
    ) -> R5OriginalKeys:
        return reserve_r5_operation_keys(
            sessions,
            settings,
            intent_id=key,
            request=wire(selected.selection),
            authority=selected,
            target=destination,
            create_request_digest=digest,
            reauthorize=lambda: (selected, destination),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = [pool.submit(reserve) for _ in range(2)]
        keys, replay = (attempt.result() for attempt in attempts)
    assert keys == replay
    assert keys.create != keys.preview
    assert reserve() == keys
    for selected, destination, digest in (
        (replace(authority, selection=a2), target, CREATE_DIGEST),
        (make_authority(b1, subject="synthetic-b"), target, CREATE_DIGEST),
        (authority, replace(target, recipient_digest="0" * 64), CREATE_DIGEST),
        (authority, target, "1" * 64),
    ):
        with pytest.raises(R5PreviewUnavailable):
            reserve(selected, intent, destination, digest)
    second_intent = uuid4()
    second = reserve(replace(authority, selection=a2), second_intent)
    assert {keys.create, keys.preview}.isdisjoint({second.create, second.preview})

    with sessions() as session:
        data = json.loads(export_owner_snapshot(session, a))["data"]["r5_preview_reservations"]
    assert len(data) == 4
    for row in data:
        assert set(row) == {
            "binding_digest",
            "created_at",
            "intent_id",
            "object_id",
            "object_revision",
            "operation",
            "original_key",
            "owner_id",
            "request_digest",
        }
        assert row["request_digest"] == (CREATE_DIGEST if row["operation"] == "create" else None)
        assert row["owner_id"] == str(a)
    with sessions() as session:
        assert (
            json.loads(export_owner_snapshot(session, b))["data"]["r5_preview_reservations"] == []
        )

    with (
        pytest.raises(DBAPIError, match="R5 preview reservations are immutable"),
        sessions() as session,
        session.begin(),
    ):
        session.execute(
            update(R5PreviewReservation)
            .where(R5PreviewReservation.original_key == keys.create)
            .values(object_revision=99)
        )
    with sessions() as session, session.begin():
        session.execute(
            delete(R5PreviewReservation).where(R5PreviewReservation.original_key == second.preview)
        )
    with pytest.raises(R5PreviewUnavailable):
        reserve(replace(authority, selection=a2), second_intent)
    with sessions() as session:
        assert len(session.scalars(select(R5PreviewReservation)).all()) == 3
    with sessions() as session:
        job = begin_owner_deletion(session, a, uuid4())
        with pytest.raises(R5PreviewUnavailable):
            reserve()
        completed = process_owner_deletion(
            session, a, job.id, LocalObjectStorage(tmp_path, max_size_bytes=1024)
        )
        assert completed.status == "completed"
    with sessions() as session:
        assert session.scalars(select(R5PreviewReservation)).all() == []
    with pytest.raises(R5PreviewUnavailable):
        reserve()
