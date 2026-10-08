"""Snapshot-bounded Today candidate and Profile-context queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from health_api.application.errors import DailyNotFound, DailySnapshotLimitExceeded
from health_api.domain.daily import local_day_bounds
from health_api.domain.daily_rollups import DailyProvenance, MetricSummaryV1, summarize_today
from health_api.domain.schemas import (
    DailyDomain,
    EventKind,
    EventSchemaV1,
    MetricKey,
    ObservationSchemaV1,
)
from health_api.persistence.models import (
    DailySnapshotMarker,
    HealthKitSourcePreference,
    HealthObject,
    HealthObjectRevision,
    ProfileItem,
    User,
)
from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.elements import ColumnElement

MAX_TODAY_OBJECTS = 10_000
MAX_PROFILE_CONTEXT_REFERENCES = 100
TODAY_QUERY_TIMEOUT_MS = 2_000


@dataclass(frozen=True)
class TodayReadSnapshot:
    as_of_sequence: int
    display_timezone: str
    revisions: tuple[HealthObjectRevision, ...]
    profile_context: tuple[tuple[UUID, str], ...]
    profile_context_truncated: bool


def owner_today_settings(
    session: Session, owner_id: UUID, *, lock_for_read: bool = False
) -> tuple[int, str]:
    statement = select(User.daily_sequence, User.display_timezone).where(
        User.id == owner_id,
        User.lifecycle == "active",
    )
    if lock_for_read:
        statement = statement.with_for_update(read=True)
    row = session.execute(statement).one_or_none()
    if row is None:
        raise DailyNotFound("owner does not exist")
    return row[0], row[1]


def healthkit_preferred_installations(session: Session, owner_id: UUID) -> dict[str, UUID]:
    return {
        resource_type: installation_id
        for resource_type, installation_id in session.execute(
            select(
                HealthKitSourcePreference.resource_type,
                HealthKitSourcePreference.device_installation_id,
            ).where(HealthKitSourcePreference.owner_id == owner_id)
        ).all()
    }


def is_today_snapshot_boundary(session: Session, owner_id: UUID, sequence: int) -> bool:
    return (
        session.scalar(
            select(DailySnapshotMarker.daily_sequence).where(
                DailySnapshotMarker.owner_id == owner_id,
                DailySnapshotMarker.daily_sequence == sequence,
            )
        )
        is not None
    )


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
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text(f"SET LOCAL statement_timeout = '{TODAY_QUERY_TIMEOUT_MS}ms'"))

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
    revision_lookup = aliased(HealthObjectRevision)
    latest_sequence = (
        select(revision_lookup.daily_sequence)
        .where(
            revision_lookup.owner_id == revision.owner_id,
            revision_lookup.object_id == revision.object_id,
            revision_lookup.daily_sequence.is_not(None),
            revision_lookup.daily_sequence <= as_of_sequence,
        )
        .order_by(revision_lookup.daily_sequence.desc())
        .limit(1)
        .correlate(revision)
        .scalar_subquery()
    )
    rows = tuple(
        session.scalars(
            select(revision)
            .where(
                revision.owner_id == owner_id,
                revision.object_id.in_(candidate_ids),
                revision.daily_sequence == latest_sequence,
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


def summarize_today_snapshot(
    revisions: tuple[HealthObjectRevision, ...],
    local_date: date,
    timezone: str,
    preferred_installations: dict[str, UUID] | None = None,
) -> list[MetricSummaryV1]:
    """Build the domain read model from the same resolved revisions as the timeline."""
    events: list[tuple[UUID, EventSchemaV1]] = []
    observations: list[tuple[UUID, ObservationSchemaV1]] = []
    linked_severity_ids: set[UUID] = set()
    provenance: dict[UUID, DailyProvenance] = {}
    for revision in revisions:
        snapshot = revision.snapshot
        source = snapshot.get("source")
        raw_metadata = snapshot.get("metadata")
        metadata: dict[str, Any] = {}
        if isinstance(raw_metadata, dict):
            metadata = raw_metadata
        provenance[revision.object_id] = DailyProvenance(
            source_kind=source.get("kind") if isinstance(source, dict) else None,
            confirmation_status=snapshot.get("confirmation_status"),
            metadata=metadata,
            revision=int(snapshot.get("revision", 1)),
        )
        if snapshot["object_type"] != "event":
            continue
        event = EventSchemaV1.model_validate(
            {
                "domain": snapshot["domain"],
                "time": snapshot["time"],
                "ended_at": snapshot.get("ended_at"),
                "payload": snapshot["payload"],
                "notes": snapshot.get("notes"),
            }
        )
        events.append((revision.object_id, event))
        if event.domain == DailyDomain.SYMPTOMS and event.payload.kind == EventKind.SYMPTOM:
            linked_severity_ids.update(
                UUID(value) for value in snapshot.get("linked_observation_ids", [])
            )

    for revision in revisions:
        snapshot = revision.snapshot
        if snapshot["object_type"] != "observation":
            continue
        observation = ObservationSchemaV1.model_validate(
            {
                "domain": snapshot["domain"],
                "time": snapshot["time"],
                "interval_end": snapshot.get("interval_end"),
                "payload": snapshot["payload"],
                "notes": snapshot.get("notes"),
            }
        )
        metric = observation.payload.value.metric
        if metric == "custom":
            # Custom tracker values are visible in the timeline but have no fixed rollup.
            continue
        if metric != MetricKey.SYMPTOM_SEVERITY or revision.object_id in linked_severity_ids:
            observations.append((revision.object_id, observation))

    return summarize_today(
        events,
        observations,
        local_date,
        timezone,
        provenance=provenance,
        preferred_installations=preferred_installations,
    )
