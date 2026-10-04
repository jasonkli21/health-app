"""Snapshot-bounded Today candidate and Profile-context queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from health_api.application.errors import DailyNotFound, DailySnapshotLimitExceeded
from health_api.domain.daily import local_day_bounds
from health_api.persistence.models import HealthObject, HealthObjectRevision, ProfileItem, User

MAX_TODAY_OBJECTS = 10_000
MAX_PROFILE_CONTEXT_REFERENCES = 100


@dataclass(frozen=True)
class TodayReadSnapshot:
    as_of_sequence: int
    display_timezone: str
    revisions: tuple[HealthObjectRevision, ...]
    profile_context: tuple[tuple[UUID, str], ...]
    profile_context_truncated: bool


def owner_today_settings(session: Session, owner_id: UUID) -> tuple[int, str]:
    row = session.execute(
        select(User.daily_sequence, User.display_timezone).where(
            User.id == owner_id,
            User.lifecycle == "active",
        )
    ).one_or_none()
    if row is None:
        raise DailyNotFound("owner does not exist")
    return row[0], row[1]


def _day_condition(local_date: date, start_at: datetime, end_at: datetime) -> ColumnElement[bool]:
    revision = HealthObjectRevision
    exact_instant = and_(
        revision.daily_time_precision == "instant",
        revision.daily_occurred_at.is_not(None),
        or_(
            and_(
                revision.daily_ended_at.is_(None),
                revision.daily_occurred_at >= start_at,
                revision.daily_occurred_at < end_at,
            ),
            and_(
                revision.daily_ended_at.is_not(None),
                revision.daily_occurred_at < end_at,
                revision.daily_ended_at > start_at,
            ),
        ),
    )
    date_only = and_(
        revision.daily_time_precision == "date_only",
        revision.daily_local_date == local_date,
    )
    return or_(exact_instant, date_only)


def load_today_snapshot(
    session: Session,
    owner_id: UUID,
    local_date: date,
    timezone: str,
    as_of_sequence: int,
    *,
    include_profile_context: bool,
) -> TodayReadSnapshot:
    if as_of_sequence < 0 or local_date == date.max:
        raise ValueError("Today snapshot bounds are invalid")
    start_at, end_at = local_day_bounds(local_date, timezone)
    revision = HealthObjectRevision
    day_condition = _day_condition(local_date, start_at, end_at)

    # Include every object ever observed in the day by this sequence. We then resolve its
    # latest revision at or below the sequence and re-check the latest time/status fields.
    candidate_ids = list(
        session.scalars(
            select(revision.object_id)
            .where(
                revision.owner_id == owner_id,
                revision.daily_sequence.is_not(None),
                revision.daily_sequence <= as_of_sequence,
                day_condition,
            )
            .distinct()
            .order_by(revision.object_id)
            .limit(MAX_TODAY_OBJECTS + 1)
        )
    )
    if len(candidate_ids) > MAX_TODAY_OBJECTS:
        raise DailySnapshotLimitExceeded
    latest = (
        select(
            revision.object_id.label("object_id"),
            func.max(revision.daily_sequence).label("daily_sequence"),
        )
        .where(
            revision.owner_id == owner_id,
            revision.daily_sequence.is_not(None),
            revision.daily_sequence <= as_of_sequence,
            revision.object_id.in_(candidate_ids),
        )
        .group_by(revision.object_id)
        .subquery()
    )
    rows = tuple(
        session.scalars(
            select(revision)
            .join(
                latest,
                and_(
                    latest.c.object_id == revision.object_id,
                    latest.c.daily_sequence == revision.daily_sequence,
                ),
            )
            .where(
                revision.owner_id == owner_id,
                revision.daily_status == "active",
                day_condition,
            )
            .order_by(revision.object_id)
            .limit(MAX_TODAY_OBJECTS + 1)
        )
    )
    if len(rows) > MAX_TODAY_OBJECTS:
        raise DailySnapshotLimitExceeded

    context_rows: tuple[tuple[UUID, str], ...] = ()
    context_truncated = False
    if include_profile_context:
        profile_query = (
            select(HealthObject.id, HealthObject.title)
            .join(
                ProfileItem,
                and_(
                    ProfileItem.owner_id == HealthObject.owner_id,
                    ProfileItem.object_id == HealthObject.id,
                ),
            )
            .where(
                HealthObject.owner_id == owner_id,
                HealthObject.object_type == "profile_item",
                HealthObject.status == "active",
                or_(HealthObject.valid_from.is_(None), HealthObject.valid_from < end_at),
                or_(HealthObject.valid_to.is_(None), HealthObject.valid_to > start_at),
            )
            .order_by(HealthObject.id)
            .limit(MAX_PROFILE_CONTEXT_REFERENCES + 1)
        )
        profiles = session.execute(profile_query).all()
        context_truncated = len(profiles) > MAX_PROFILE_CONTEXT_REFERENCES
        context_rows = tuple(profiles[:MAX_PROFILE_CONTEXT_REFERENCES])

    return TodayReadSnapshot(
        as_of_sequence=as_of_sequence,
        display_timezone=timezone,
        revisions=rows,
        profile_context=context_rows,
        profile_context_truncated=context_truncated,
    )
