from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_api.application.ai_context_admission import _eligibility_conditions
from health_api.application.daily_service import (
    CreateDailyEntry,
    CreateDailyEvent,
    create_daily_entry,
    update_daily_item,
)
from health_api.application.personal_ai_context import read_personal_ai_health_context
from health_api.application.personal_ai_federation_export import (
    HealthFederationExportDenied,
    read_health_federation_export,
)
from health_api.application.profile_service import (
    CreateProfile,
    create_profile_item,
    update_profile_item,
)
from health_api.domain.schemas import EventSchemaV1, ProfilePayloadV1, ProfileValidity
from health_api.integrations.federation_export import HealthFederationExportRequest
from health_api.integrations.personal_ai_context import (
    HealthContextEntityReference,
    HealthContextReadRequest,
)
from health_api.persistence.models import HealthObject, ProfileItem, ProviderIdentity, User

OWNER_ID = UUID("00000000-0000-0000-0000-000000000929")
FIREBASE_ISSUER = "https://securetoken.google.com/health-test1"


def _seed_owner(session: Session) -> None:
    session.add(User(id=OWNER_ID, display_timezone="America/Los_Angeles"))
    session.add(
        ProviderIdentity(
            issuer=FIREBASE_ISSUER,
            subject="phase29-firebase-subject",
            user_id=OWNER_ID,
        )
    )
    session.flush()


def _profile(
    *, category: str, label: str, key: str, cross_domain_use_allowed: bool
) -> CreateProfile:
    return CreateProfile(
        id=uuid4(),
        profile=ProfilePayloadV1.model_validate(
            {
                "kind": "preference" if category == "preferences" else "fact",
                "category": category,
                "key": key,
                "label": label,
                "value": {"type": "text", "value": "synthetic phase 29 value"},
            }
        ),
        validity=ProfileValidity(),
        ai_use_allowed=True,
        cross_domain_use_allowed=cross_domain_use_allowed,
        notes="synthetic record note",
    )


def _federation_profile(*, key: str, value: object, share: bool = True) -> CreateProfile:
    return CreateProfile(
        id=uuid4(),
        profile=ProfilePayloadV1.model_validate(
            {
                "kind": "constraint",
                "category": "constraints",
                "key": key,
                "label": f"Synthetic {key.replace('_', ' ')}",
                "value": value,
            }
        ),
        validity=ProfileValidity(),
        ai_use_allowed=True,
        cross_domain_use_allowed=share,
    )


def _federation_request(entity_id: UUID, *, field: str = "dietary_restrictions"):
    purpose, destination = (
        ("health_dietary_restrictions_to_travel", "travel")
        if field == "dietary_restrictions"
        else ("health_ergonomic_constraints_to_shopping", "shopping")
    )
    return HealthFederationExportRequest(
        operation="read",
        category=field,
        entity_id=entity_id,
        purpose=purpose,
        destination_application_id=destination,
        fields=(field,),
    )


def test_catalog_and_profile_read_require_both_health_permissions(db_session: Session) -> None:
    _seed_owner(db_session)
    shared = create_profile_item(
        db_session,
        OWNER_ID,
        _profile(
            category="background",
            label="Synthetic background",
            key="phase29_background",
            cross_domain_use_allowed=True,
        ),
    ).aggregate[0]
    local_only = create_profile_item(
        db_session,
        OWNER_ID,
        _profile(
            category="preferences",
            label="Synthetic local preference",
            key="phase29_local_preference",
            cross_domain_use_allowed=False,
        ),
    ).aggregate[0]
    db_session.commit()

    now = datetime.now(UTC)
    catalog = read_personal_ai_health_context(
        db_session, OWNER_ID, HealthContextReadRequest(operation="catalog"), now=now
    )
    assert [option.category for option in catalog.categories] == ["profile_background"]
    local_only_read = read_personal_ai_health_context(
        db_session,
        OWNER_ID,
        HealthContextReadRequest(
            operation="profile",
            category="profile_preferences",
            fields=("record",),
            entity_refs=(
                HealthContextEntityReference(object_type="profile_item", object_id=local_only.id),
            ),
        ),
        now=now,
    )
    assert local_only_read.items == ()

    profile = read_personal_ai_health_context(
        db_session,
        OWNER_ID,
        HealthContextReadRequest(
            operation="profile",
            category="profile_background",
            fields=("record", "notes", "source_kind", "confirmation_status", "validity"),
            max_results=4,
            max_bytes=8192,
        ),
        now=now,
    )
    assert len(profile.items) == 1
    result = profile.items[0]
    assert result.object_id == shared.id
    assert result.payload.category == "profile_background"
    assert result.payload.object_type == "profile_item"
    assert result.payload.record["key"] == "phase29_background"
    assert result.sensitivity == "restricted"
    assert result.authority == "authoritative"
    assert result.field_sensitivity
    assert result.source_refs[0].fingerprint == result.source_refs[1].fingerprint
    assert result.permission_dependencies[0].permission_id == (
        f"health_context_read:profile_background:profile_item:{shared.id}"
    )

    update_profile_item(
        db_session,
        OWNER_ID,
        shared.id,
        shared.revision,
        {"cross_domain_use_allowed": False},
    )
    catalog_after_revoke = read_personal_ai_health_context(
        db_session, OWNER_ID, HealthContextReadRequest(operation="catalog"), now=now
    )
    assert catalog_after_revoke.categories == ()
    verification = read_personal_ai_health_context(
        db_session,
        OWNER_ID,
        HealthContextReadRequest(
            operation="verify",
            category="profile_background",
            entity_refs=(
                HealthContextEntityReference(object_type="profile_item", object_id=shared.id),
            ),
            fields=("permission_version",),
            max_results=1,
            max_bytes=4096,
        ),
        now=now,
    )
    assert verification.permission_versions == ()

    # The cross-service grant is additional to local AI use; revoking it does not
    # alter the local preview's established ai_use_allowed rule.
    local_object = db_session.get(HealthObject, local_only.id)
    assert local_object is not None and local_object.ai_use_allowed is True
    local_candidate = db_session.scalar(
        select(HealthObject.id).where(
            *_eligibility_conditions(
                OWNER_ID,
                object_type="profile_item",
                payload=ProfileItem.payload,
                as_of=now,
                start_date=now.date(),
                start_at=now,
                end_date=now.date(),
            )
        )
    )
    assert local_candidate == local_only.id


def test_health_federation_export_is_narrow_owner_scoped_revisioned_and_revocable(
    db_session: Session,
) -> None:
    _seed_owner(db_session)
    shared = create_profile_item(
        db_session,
        OWNER_ID,
        _federation_profile(
            key="dietary_restrictions",
            value={"type": "text_list", "value": ["synthetic allergy"]},
        ),
    ).aggregate[0]
    empty = create_profile_item(
        db_session,
        OWNER_ID,
        _federation_profile(key="ergonomic_constraints", value=None),
    ).aggregate[0]
    db_session.commit()

    response = read_health_federation_export(
        db_session,
        OWNER_ID,
        _federation_request(shared.id),
        now=datetime.now(UTC),
    )
    assert response.complete is True
    assert response.authoritative_empty is False
    assert response.continuation is None
    assert response.item.category == "dietary_restrictions"
    assert response.item.payload.model_dump() == {
        "dietary_restrictions": ("synthetic allergy",)
    }
    assert response.item.sensitivity == "restricted"
    assert response.item.source_revision == shared.revision
    assert response.item.permission_dependencies[0].version.endswith(
        f"r{shared.revision}:ai1:cross1"
    )
    assert response.item.permission_dependencies[0].destination_application_id == "travel"
    assert {reference.kind for reference in response.item.source_refs} == {"record", "source"}

    authoritative_empty = read_health_federation_export(
        db_session,
        OWNER_ID,
        _federation_request(empty.id, field="ergonomic_constraints"),
        now=datetime.now(UTC),
    )
    assert authoritative_empty.complete is True
    assert authoritative_empty.authoritative_empty is True
    assert authoritative_empty.item.payload.model_dump() == {"ergonomic_constraints": None}

    with pytest.raises(HealthFederationExportDenied):
        read_health_federation_export(
            db_session,
            uuid4(),
            _federation_request(shared.id),
            now=datetime.now(UTC),
        )
    with pytest.raises(HealthFederationExportDenied):
        read_health_federation_export(
            db_session,
            OWNER_ID,
            _federation_request(uuid4()),
            now=datetime.now(UTC),
        )

    update_profile_item(
        db_session,
        OWNER_ID,
        shared.id,
        expected_revision=shared.revision,
        changes={"cross_domain_use_allowed": False},
    )
    db_session.flush()
    verify = HealthFederationExportRequest(
        operation="verify",
        category="dietary_restrictions",
        entity_id=shared.id,
        purpose="health_dietary_restrictions_to_travel",
        destination_application_id="travel",
        fields=("permission_version",),
    )
    with pytest.raises(HealthFederationExportDenied):
        read_health_federation_export(
            db_session, OWNER_ID, verify, now=datetime.now(UTC)
        )


def test_bounded_daily_read_preserves_time_units_quality_and_unknown_uncertainty(
    db_session: Session,
) -> None:
    _seed_owner(db_session)
    now = datetime.now(UTC)
    occurred_at = now - timedelta(minutes=5)
    event = EventSchemaV1.model_validate(
        {
            "domain": "nutrition",
            "time": {
                "precision": "instant",
                "occurred_at": occurred_at.isoformat(),
                "timezone": "America/Los_Angeles",
            },
            "ended_at": None,
            "payload": {
                "kind": "meal",
                "label": "Synthetic Health context meal",
                "foods": ["synthetic rice"],
                "energy": {"value": 120, "unit": "kcal"},
            },
            "notes": None,
        }
    )
    object_id = uuid4()
    result = create_daily_entry(
        db_session,
        OWNER_ID,
        CreateDailyEntry(
            events=(CreateDailyEvent(id=object_id, event=event, ai_use_allowed=True),)
        ),
    )
    assert result.events[0][0].cross_domain_use_allowed is False

    request = HealthContextReadRequest(
        operation="history",
        category="nutrition",
        fields=(
            "record",
            "domain",
            "notes",
            "time",
            "interval_end",
            "units",
            "source_kind",
            "confirmation_status",
            "quality",
            "uncertainty",
        ),
        window_start=now - timedelta(days=1),
        window_end=now,
        max_results=4,
        max_bytes=16_384,
    )
    denied = read_personal_ai_health_context(db_session, OWNER_ID, request, now=now)
    assert denied.items == ()

    update_daily_item(
        db_session,
        OWNER_ID,
        object_id,
        expected_revision=1,
        record=event,
        cross_domain_use_allowed=True,
    )

    response = read_personal_ai_health_context(db_session, OWNER_ID, request, now=now)
    assert len(response.items) == 1
    item = response.items[0]
    assert item.object_id == object_id
    assert item.payload.domain == "nutrition"
    assert item.payload.time.occurred_at == occurred_at
    assert item.payload.units == {"energy": "kcal"}
    assert item.payload.quality == {}
    assert item.payload.uncertainty is None


def test_daily_consent_regrant_advances_health_permission_dependency_epoch(
    db_session: Session,
) -> None:
    _seed_owner(db_session)
    now = datetime.now(UTC)
    occurred_at = now - timedelta(minutes=5)
    event = EventSchemaV1.model_validate(
        {
            "domain": "nutrition",
            "time": {
                "precision": "instant",
                "occurred_at": occurred_at.isoformat(),
                "timezone": "America/Los_Angeles",
            },
            "ended_at": None,
            "payload": {
                "kind": "meal",
                "label": "Synthetic consent epoch meal",
                "foods": ["synthetic consent epoch food"],
                "energy": {"value": 120, "unit": "kcal"},
            },
            "notes": None,
        }
    )
    object_id = uuid4()
    created = create_daily_entry(
        db_session,
        OWNER_ID,
        CreateDailyEntry(
            events=(
                CreateDailyEvent(
                    id=object_id,
                    event=event,
                    ai_use_allowed=True,
                    cross_domain_use_allowed=True,
                ),
            )
        ),
    )
    assert created.events[0][0].revision == 1
    request = HealthContextReadRequest(
        operation="history",
        category="nutrition",
        fields=("record",),
        window_start=now - timedelta(days=1),
        window_end=now,
        max_results=8,
        max_bytes=8192,
    )
    initial = read_personal_ai_health_context(db_session, OWNER_ID, request, now=now)
    old_version = initial.items[0].permission_dependencies[0].version

    revoked = update_daily_item(
        db_session,
        OWNER_ID,
        object_id,
        expected_revision=1,
        record=event,
        cross_domain_use_allowed=False,
    )
    assert revoked[0].revision == 2
    verify_request = HealthContextReadRequest(
        operation="verify",
        category="nutrition",
        entity_refs=(HealthContextEntityReference(object_type="event", object_id=object_id),),
        fields=("permission_version",),
        max_results=1,
        max_bytes=4096,
    )
    assert (
        read_personal_ai_health_context(
            db_session, OWNER_ID, verify_request, now=now
        ).permission_versions
        == ()
    )

    regranted = update_daily_item(
        db_session,
        OWNER_ID,
        object_id,
        expected_revision=2,
        record=event,
        cross_domain_use_allowed=True,
    )
    assert regranted[0].revision == 3
    current = read_personal_ai_health_context(db_session, OWNER_ID, request, now=now)
    current_version = current.items[0].permission_dependencies[0].version
    verification = read_personal_ai_health_context(db_session, OWNER_ID, verify_request, now=now)
    assert verification.permission_versions[0].version == current_version
    assert current_version != old_version


def test_daily_history_future_and_overlong_windows_are_rejected() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="health_context_window_too_large"):
        HealthContextReadRequest(
            operation="history",
            category="sleep",
            fields=("record",),
            window_start=now - timedelta(days=91),
            window_end=now,
        )
