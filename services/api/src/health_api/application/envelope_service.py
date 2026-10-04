"""Shared canonical envelope mechanics used by Profile and daily writes."""

from __future__ import annotations

from uuid import UUID

from health_api.application.errors import DailyNotFound
from health_api.persistence.models import Source, User
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session


def manual_source(session: Session, owner_id: UUID) -> Source:
    """Resolve the one server-owned manual provenance row for this principal."""
    session.execute(
        insert(Source)
        .values(
            owner_id=owner_id,
            source_key="manual",
            source_kind="manual",
            display_name="Manual entry",
        )
        .on_conflict_do_nothing(index_elements=[Source.owner_id, Source.source_key])
    )
    source = session.scalar(
        select(Source).where(Source.owner_id == owner_id, Source.source_key == "manual")
    )
    if source is None:
        raise RuntimeError("manual source could not be resolved")
    return source


def next_daily_sequence(session: Session, owner_id: UUID) -> int:
    """Allocate one monotonic snapshot number; the owner row lock serializes daily writes."""
    value = session.scalar(
        update(User)
        .where(User.id == owner_id)
        .values(daily_sequence=User.daily_sequence + 1)
        .returning(User.daily_sequence)
    )
    if value is None:
        raise DailyNotFound("owner does not exist")
    return value
