"""Shared canonical envelope mechanics used by Profile and daily writes."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from health_api.application.errors import DailyNotFound
from health_api.persistence.models import DailySnapshotMarker, Source, User


@contextmanager
def unit_of_work(session: Session) -> Iterator[None]:
    """Compose a domain command inside an outer transaction without nested commits."""
    if session.in_transaction():
        with session.begin_nested():
            yield
    else:
        with session.begin():
            yield


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


def proposal_source(
    session: Session,
    owner_id: UUID,
    proposal_id: UUID,
    origin_kind: str,
) -> Source:
    """Create the immutable provenance source applied to every target in a proposal."""
    source_kind = "ai" if origin_kind == "ai" else "manual"
    source_key = f"proposal:{proposal_id}"
    session.execute(
        insert(Source)
        .values(
            owner_id=owner_id,
            source_key=source_key,
            source_kind=source_kind,
            display_name="AI proposal" if source_kind == "ai" else "Confirmed proposal",
            external_namespace="personal-ai" if source_kind == "ai" else None,
            external_identifier=str(proposal_id) if source_kind == "ai" else None,
        )
        .on_conflict_do_nothing(index_elements=[Source.owner_id, Source.source_key])
    )
    source = session.scalar(
        select(Source).where(Source.owner_id == owner_id, Source.source_key == source_key)
    )
    if source is None or source.source_kind != source_kind:
        raise RuntimeError("proposal source could not be resolved")
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
    session.add(DailySnapshotMarker(owner_id=owner_id, daily_sequence=value))
    return value
