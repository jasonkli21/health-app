"""Deterministic bounded local-calendar schedule expansion."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from health_api.domain.planning import ScheduleDefinitionV1, ScheduleRecurrence


def resolve_local_time(local_value: datetime, timezone: str) -> tuple[datetime, str]:
    """Resolve a local slot once: next valid minute for gaps, earlier instant for overlaps."""
    zone = ZoneInfo(timezone)
    naive = local_value.replace(tzinfo=None)
    for offset_minutes in range(181):
        candidate_local = naive + timedelta(minutes=offset_minutes)
        candidates: list[datetime] = []
        for fold in (0, 1):
            candidate = candidate_local.replace(tzinfo=zone, fold=fold)
            round_trip = candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
            instant = candidate.astimezone(UTC)
            if round_trip == candidate_local and all(
                item.astimezone(UTC) != instant for item in candidates
            ):
                candidates.append(candidate)
        if candidates:
            instants = sorted(item.astimezone(UTC) for item in candidates)
            if offset_minutes:
                resolution = "next_valid_time"
            elif len(instants) > 1:
                resolution = "earlier_offset"
            else:
                resolution = "exact"
            return instants[0], resolution
    raise ValueError("local schedule time could not be resolved")


def schedule_matches_day(definition: ScheduleDefinitionV1, local_date: date) -> bool:
    if local_date < definition.start_date or (
        definition.end_date and local_date > definition.end_date
    ):
        return False
    if definition.recurrence == ScheduleRecurrence.DAILY:
        return (local_date - definition.start_date).days % definition.interval == 0
    start_week = definition.start_date - timedelta(days=definition.start_date.weekday())
    current_week = local_date - timedelta(days=local_date.weekday())
    weeks = (current_week - start_week).days // 7
    return weeks % definition.interval == 0 and local_date.weekday() in definition.weekdays


def expand_schedule(
    definition: ScheduleDefinitionV1,
    start_date: date,
    end_date: date,
    *,
    schedule_id: str,
    revision: int,
    parent_id: str,
    item_id: str | None,
) -> list[dict[str, object]]:
    if end_date < start_date or (end_date - start_date).days >= 31:
        raise ValueError("schedule window must span at most 31 calendar days")
    slots: list[dict[str, object]] = []
    current = start_date
    while current <= end_date:
        if schedule_matches_day(definition, current):
            local_value = datetime.combine(current, definition.local_time)
            due_at, resolution = resolve_local_time(local_value, definition.timezone)
            slots.append(
                {
                    "schedule_id": schedule_id,
                    "schedule_revision": revision,
                    "parent_id": parent_id,
                    "item_id": item_id,
                    "local_date": current,
                    "local_time": definition.local_time,
                    "timezone": definition.timezone,
                    "due_at": due_at,
                    "dst_resolution": resolution,
                }
            )
        current += timedelta(days=1)
    return slots
