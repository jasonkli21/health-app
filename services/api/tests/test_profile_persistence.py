from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from health_api.application import profile_service
from health_api.application.errors import ProfileConflict, ProfileNotFound, ProfileValidationError
from health_api.application.local_principal import ensure_local_principal
from health_api.application.profile_service import (
    CreateProfile,
    archive_profile_item,
    create_profile_item,
    create_profile_relationship,
    get_profile_item,
    list_profile_history,
    list_profile_items,
    list_profile_relationships,
    remove_profile_relationship,
    update_profile_item,
)
from health_api.config.settings import Settings
from health_api.domain.schemas import ProfilePayloadV1, ProfileValidity
from health_api.persistence.models import (
    HealthObjectRevision,
    HealthRelationship,
    ProfileItem,
    Source,
    User,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker


def payload(label: str = "Diet preference", value: object = None) -> ProfilePayloadV1:
    return ProfilePayloadV1.model_validate(
        {
            "kind": "fact",
            "category": "background",
            "key": "diet_preference",
            "label": label,
            "value": value,
        }
    )


def create_command(
    item_id: UUID | None = None,
    label: str = "Diet preference",
    value: object = None,
    *,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
) -> CreateProfile:
    return CreateProfile(
        id=item_id or uuid4(),
        profile=payload(label, value),
        validity=ProfileValidity(valid_from=valid_from, valid_to=valid_to),
    )


def new_principal(session: Session, principal_id: UUID | None = None) -> UUID:
    identity = principal_id or uuid4()
    settings = Settings(
        _env_file=None,
        app_env="test",
        auth_mode="dev",
        local_principal_id=identity,
    )
    resolved = ensure_local_principal(session, settings)
    assert resolved == identity
    return identity


def test_create_retry_after_edit_returns_current_without_reverting_it(db_session: Session) -> None:
    owner = new_principal(db_session)
    command = create_command(value={"type": "boolean", "value": False})

    first = create_profile_item(db_session, owner, command)
    retry = create_profile_item(db_session, owner, command)
    assert first.created is True
    assert retry.created is False
    assert retry.aggregate[0].revision == 1
    assert retry.aggregate[1].payload["value"] == {"type": "boolean", "value": False}

    edited = update_profile_item(
        db_session,
        owner,
        command.id,
        1,
        {"profile": payload("Plant based", {"type": "text", "value": "Plant based"})},
    )
    retried_after_edit = create_profile_item(db_session, owner, command)
    assert edited[0].revision == 2
    assert retried_after_edit.aggregate[0].revision == 2
    assert retried_after_edit.aggregate[1].payload["label"] == "Plant based"
    assert (
        db_session.scalar(
            select(HealthObjectRevision.revision).where(
                HealthObjectRevision.owner_id == owner,
                HealthObjectRevision.object_id == command.id,
                HealthObjectRevision.revision == 3,
            )
        )
        is None
    )
    db_session.commit()

    with pytest.raises(ProfileConflict):
        create_profile_item(db_session, owner, create_command(command.id, label="Different"))


def test_create_persists_restrictive_permissions_and_bounded_metadata(db_session: Session) -> None:
    owner = new_principal(db_session)
    command = CreateProfile(
        id=uuid4(),
        profile=payload(),
        validity=ProfileValidity(),
        metadata={"display_unit": "kg", "sort_order": 0},
    )
    created = create_profile_item(db_session, owner, command).aggregate[0]
    assert created.metadata_json == {"display_unit": "kg", "sort_order": 0}
    assert created.ai_use_allowed is False
    assert created.cross_domain_use_allowed is False

    with pytest.raises(ProfileValidationError):
        create_profile_item(
            db_session,
            owner,
            CreateProfile(
                id=uuid4(),
                profile=payload(),
                validity=ProfileValidity(),
                metadata={"not_finite": float("nan")},
            ),
        )


def test_owner_scoping_applies_to_detail_and_history(db_session: Session) -> None:
    owner_a = new_principal(db_session)
    owner_b = new_principal(db_session)
    item_a = create_profile_item(db_session, owner_a, create_command()).aggregate[0]
    item_b = create_profile_item(db_session, owner_b, create_command()).aggregate[0]

    assert get_profile_item(db_session, owner_a, item_a.id)[0].owner_id == owner_a
    with pytest.raises(ProfileNotFound):
        get_profile_item(db_session, owner_a, item_b.id)
    with pytest.raises(ProfileNotFound):
        list_profile_history(db_session, owner_a, item_b.id, after_revision=0, limit=10)
    assert [
        row[0].id
        for row in list_profile_items(
            db_session, owner_a, datetime.now(UTC), category=None, limit=10
        )
    ] == [item_a.id]


def test_temporal_query_uses_inclusive_start_exclusive_end_and_unbounded_nulls(
    db_session: Session,
) -> None:
    owner = new_principal(db_session)
    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 10, 3, tzinfo=UTC)
    bounded = create_profile_item(
        db_session, owner, create_command(valid_from=start, valid_to=end)
    ).aggregate[0]
    unbounded = create_profile_item(db_session, owner, create_command()).aggregate[0]

    at_start = list_profile_items(db_session, owner, start, None, 10)
    at_end = list_profile_items(db_session, owner, end, None, 10)
    assert {row[0].id for row in at_start} == {bounded.id, unbounded.id}
    assert {row[0].id for row in at_end} == {unbounded.id}


def test_patch_and_archive_append_history_and_hide_archived_from_active_list(
    db_session: Session,
) -> None:
    owner = new_principal(db_session)
    created = create_profile_item(db_session, owner, create_command()).aggregate[0]
    changed = update_profile_item(
        db_session,
        owner,
        created.id,
        1,
        {"notes": "Updated from the user profile screen", "ai_use_allowed": True},
    )
    assert changed[0].revision == 2
    assert changed[0].ai_use_allowed is True

    with pytest.raises(ProfileConflict):
        update_profile_item(db_session, owner, created.id, 1, {"notes": "stale"})
    assert len(list_profile_history(db_session, owner, created.id, 0, 10)) == 2
    db_session.commit()

    archived = archive_profile_item(db_session, owner, created.id, 2)
    history = list_profile_history(db_session, owner, created.id, 0, 10)
    assert archived[0].status == "archived"
    assert archived[0].revision == 3
    assert [revision.revision for revision in history] == [1, 2, 3]
    assert [revision.snapshot["status"] for revision in history] == ["active", "active", "archived"]
    assert list_profile_items(db_session, owner, datetime.now(UTC), None, 10) == []
    assert get_profile_item(db_session, owner, created.id)[0].status == "archived"


def test_failed_history_insert_rolls_back_envelope_and_payload(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = new_principal(db_session)
    created = create_profile_item(db_session, owner, create_command()).aggregate[0]

    def fail_revision(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic history failure")

    monkeypatch.setattr(profile_service, "_append_revision", fail_revision)
    with pytest.raises(RuntimeError, match="history failure"):
        update_profile_item(db_session, owner, created.id, 1, {"notes": "partial"})

    current = get_profile_item(db_session, owner, created.id)
    assert current[0].revision == 1
    assert current[0].notes is None
    assert len(list_profile_history(db_session, owner, created.id, 0, 10)) == 1


def test_concurrent_stale_edits_allow_only_one_revision(db_session: Session) -> None:
    owner = new_principal(db_session)
    created = create_profile_item(db_session, owner, create_command()).aggregate[0]
    session_factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    barrier = Barrier(2)

    def edit(label: str) -> str:
        with session_factory() as session:
            barrier.wait(timeout=10)
            try:
                update_profile_item(
                    session,
                    owner,
                    created.id,
                    1,
                    {"profile": payload(label, {"type": "text", "value": label})},
                )
                return "updated"
            except ProfileConflict:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(edit, ["Option A", "Option B"]))
    assert sorted(results) == ["conflict", "updated"]
    db_session.expire_all()
    assert get_profile_item(db_session, owner, created.id)[0].revision == 2
    assert [
        entry.revision for entry in list_profile_history(db_session, owner, created.id, 0, 10)
    ] == [1, 2]


def test_relationships_are_owner_scoped_typed_and_removable(db_session: Session) -> None:
    owner = new_principal(db_session)
    other = new_principal(db_session)
    left = create_profile_item(db_session, owner, create_command()).aggregate[0]
    right = create_profile_item(db_session, owner, create_command()).aggregate[0]
    foreign = create_profile_item(db_session, other, create_command()).aggregate[0]
    validity = ProfileValidity()

    edge = create_profile_relationship(db_session, owner, left.id, right.id, "related_to", validity)
    edge_id = edge.id
    assert [relation.id for relation in list_profile_relationships(db_session, owner, left.id)] == [
        edge_id
    ]
    db_session.commit()
    with pytest.raises(ProfileNotFound):
        create_profile_relationship(db_session, owner, left.id, foreign.id, "related_to", validity)
    db_session.rollback()
    with pytest.raises(ProfileValidationError):
        create_profile_relationship(db_session, owner, left.id, right.id, "causes", validity)
    with pytest.raises(ProfileValidationError):
        create_profile_relationship(db_session, owner, left.id, left.id, "related_to", validity)
    db_session.rollback()
    with pytest.raises(ProfileNotFound):
        remove_profile_relationship(db_session, other, edge_id)
    db_session.rollback()
    remove_profile_relationship(db_session, owner, edge_id)
    assert list_profile_relationships(db_session, owner, left.id) == []


def test_postgres_composite_foreign_keys_reject_cross_owner_relationships(
    db_session: Session,
) -> None:
    owner_a = new_principal(db_session)
    owner_b = new_principal(db_session)
    left = create_profile_item(db_session, owner_a, create_command()).aggregate[0]
    foreign = create_profile_item(db_session, owner_b, create_command()).aggregate[0]
    source_id = db_session.scalar(
        select(Source.id).where(Source.owner_id == owner_a, Source.source_key == "manual")
    )
    assert source_id is not None

    db_session.add(
        HealthRelationship(
            owner_id=owner_a,
            from_object_id=left.id,
            to_object_id=foreign.id,
            relation_type="related_to",
            source_id=source_id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_users_and_relational_owner_keys_are_real_database_rows(db_session: Session) -> None:
    owner = new_principal(db_session)
    created = create_profile_item(db_session, owner, create_command()).aggregate[0]
    assert db_session.get(User, owner) is not None
    assert (
        db_session.scalar(
            select(ProfileItem.object_id).where(
                ProfileItem.owner_id == owner, ProfileItem.object_id == created.id
            )
        )
        == created.id
    )
