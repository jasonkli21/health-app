from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from health_api.application.ai_context_admission import _eligibility_conditions
from health_api.application.daily_service import (
    CreateDailyEntry,
    CreateDailyEvent,
    create_daily_entry,
)
from health_api.application.personal_ai_context import read_personal_ai_health_context
from health_api.application.profile_service import CreateProfile, create_profile_item
from health_api.domain.schemas import EventSchemaV1, ProfilePayloadV1, ProfileValidity
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
                HealthContextEntityReference(
                    object_type="profile_item", object_id=local_only.id
                ),
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

    db_session.execute(
        update(HealthObject)
        .where(HealthObject.owner_id == OWNER_ID, HealthObject.id == shared.id)
        .values(cross_domain_use_allowed=False)
    )
    db_session.commit()
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

    db_session.execute(
        update(HealthObject)
        .where(HealthObject.owner_id == OWNER_ID, HealthObject.id == object_id)
        .values(cross_domain_use_allowed=True)
    )
    db_session.commit()

    response = read_personal_ai_health_context(db_session, OWNER_ID, request, now=now)
    assert len(response.items) == 1
    item = response.items[0]
    assert item.object_id == object_id
    assert item.payload.domain == "nutrition"
    assert item.payload.time.occurred_at == occurred_at
    assert item.payload.units == {"energy": "kcal"}
    assert item.payload.quality == {}
    assert item.payload.uncertainty is None


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
