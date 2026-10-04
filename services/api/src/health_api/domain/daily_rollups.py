"""Versioned sparse summaries over validated Event and Observation schemas."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from health_api.domain.daily import (
    TODAY_METHOD_VERSION,
    UNIT_CONVERSION_VERSION,
    canonical_unit,
    convert_value,
    interval_overlap_seconds,
    local_day_bounds,
)
from health_api.domain.schemas import (
    DailyDomain,
    DateOnlyTimePoint,
    EventKind,
    EventSchemaV1,
    InstantTimePoint,
    MetricKey,
    ObservationSchemaV1,
    StrictModel,
)
from pydantic import Field


class CoverageV1(StrictModel):
    known_count: Annotated[int, Field(ge=0)]
    total_count: Annotated[int, Field(ge=0)]


class MetricSummaryV1(StrictModel):
    domain: DailyDomain
    metric: MetricKey
    known_value: float | None
    unit: str
    logged_count: Annotated[int, Field(ge=0)]
    coverage: CoverageV1
    method_version: str
    partial: bool


def _event_on_day(
    event: EventSchemaV1,
    local_date: date,
    timezone: str,
) -> bool:
    start, end = local_day_bounds(local_date, timezone)
    if isinstance(event.time, DateOnlyTimePoint):
        # Keep the user's entered calendar date; never fabricate a sample at midnight.
        return event.time.local_date == local_date
    occurred_at = event.time.occurred_at.astimezone(UTC)
    if event.ended_at is not None:
        return interval_overlap_seconds(occurred_at, event.ended_at, start, end) > 0
    return start <= occurred_at < end


def _observation_on_day(
    observation: ObservationSchemaV1,
    local_date: date,
    timezone: str,
) -> bool:
    start, end = local_day_bounds(local_date, timezone)
    if isinstance(observation.time, DateOnlyTimePoint):
        return observation.time.local_date == local_date
    observed_at = observation.time.occurred_at.astimezone(UTC)
    if observation.interval_end is not None:
        return interval_overlap_seconds(observed_at, observation.interval_end, start, end) > 0
    return start <= observed_at < end


def _observation_order(
    observation: ObservationSchemaV1,
    local_date: date,
    timezone: str,
    object_id: UUID,
) -> tuple[date, int, datetime, str]:
    """Order by observed calendar date, then exact instant when one was supplied, then ID."""
    if isinstance(observation.time, DateOnlyTimePoint):
        return observation.time.local_date, 0, datetime.min.replace(tzinfo=UTC), str(object_id)
    instant = observation.time.occurred_at.astimezone(ZoneInfo(timezone))
    return instant.date(), 1, instant.astimezone(UTC), str(object_id)


def _summary(
    domain: DailyDomain,
    metric: MetricKey,
    values: list[float],
    logged_count: int,
    method: str,
    *,
    latest: bool = False,
) -> MetricSummaryV1:
    known_count = logged_count if latest and values else len(values)
    known_value = (values[-1] if latest else sum(values)) if values else None
    return MetricSummaryV1(
        domain=domain,
        metric=metric,
        known_value=known_value,
        unit=canonical_unit(metric).value,
        logged_count=logged_count,
        coverage=CoverageV1(known_count=known_count, total_count=logged_count),
        method_version=f"{TODAY_METHOD_VERSION}/{method}/{UNIT_CONVERSION_VERSION}",
        partial=logged_count > 0 and known_count < logged_count,
    )


def _event_starts_on_day(event: EventSchemaV1, local_date: date, timezone: str) -> bool:
    if isinstance(event.time, DateOnlyTimePoint):
        return event.time.local_date == local_date
    start, end = local_day_bounds(local_date, timezone)
    occurred_at = event.time.occurred_at.astimezone(UTC)
    return start <= occurred_at < end


def summarize_today(
    events: list[tuple[UUID, EventSchemaV1]],
    observations: list[tuple[UUID, ObservationSchemaV1]],
    local_date: date,
    timezone: str,
) -> list[MetricSummaryV1]:
    """Compute fixed metric summaries; absent values stay null and explicit zero stays zero."""
    day_events = [
        (object_id, event)
        for object_id, event in events
        if _event_on_day(event, local_date, timezone)
    ]
    day_observations = [
        (object_id, observation)
        for object_id, observation in observations
        if _observation_on_day(observation, local_date, timezone)
    ]
    by_domain: dict[DailyDomain, list[EventSchemaV1]] = defaultdict(list)
    for _, event in day_events:
        by_domain[event.domain].append(event)

    energy_values: list[float] = []
    for event in by_domain[DailyDomain.NUTRITION]:
        if event.payload.kind == EventKind.MEAL and event.payload.energy is not None:
            energy_values.append(
                convert_value(
                    MetricKey.ENERGY,
                    event.payload.energy.value,
                    event.payload.energy.unit,
                )
            )
    result = [
        _summary(
            DailyDomain.NUTRITION,
            MetricKey.ENERGY,
            energy_values,
            len(by_domain[DailyDomain.NUTRITION]),
            "sum-known-v1",
        )
    ]

    workouts = by_domain[DailyDomain.EXERCISE]
    day_start, day_end = local_day_bounds(local_date, timezone)
    duration_values: list[float] = []
    distance_values: list[float] = []
    for event in workouts:
        if event.payload.kind != EventKind.WORKOUT:
            continue
        if event.ended_at is not None and isinstance(event.time, InstantTimePoint):
            overlap = interval_overlap_seconds(
                event.time.occurred_at, event.ended_at, day_start, day_end
            )
            duration_values.append(overlap / 60.0)
        elif event.payload.duration is not None:
            duration_values.append(
                convert_value(
                    MetricKey.DURATION,
                    event.payload.duration.value,
                    event.payload.duration.unit,
                )
            )
        if event.payload.distance is not None and _event_starts_on_day(event, local_date, timezone):
            distance_values.append(
                convert_value(
                    MetricKey.DISTANCE,
                    event.payload.distance.value,
                    event.payload.distance.unit,
                )
            )
    result.extend(
        [
            _summary(
                DailyDomain.EXERCISE,
                MetricKey.DURATION,
                duration_values,
                len(workouts),
                "sum-workout-duration-v1",
            ),
            _summary(
                DailyDomain.EXERCISE,
                MetricKey.DISTANCE,
                distance_values,
                len(workouts),
                "sum-start-day-v1",
            ),
            _summary(
                DailyDomain.SLEEP,
                MetricKey.DURATION,
                [
                    interval_overlap_seconds(
                        event.time.occurred_at, event.ended_at, day_start, day_end
                    )
                    / 60.0
                    for event in by_domain[DailyDomain.SLEEP]
                    if event.ended_at is not None and isinstance(event.time, InstantTimePoint)
                ],
                len(by_domain[DailyDomain.SLEEP]),
                "sum-overlap-v1",
            ),
        ]
    )

    metric_observations: dict[MetricKey, list[tuple[UUID, ObservationSchemaV1, float]]] = (
        defaultdict(list)
    )
    for object_id, observation in day_observations:
        value = observation.payload.value
        metric = value.metric
        normalized = convert_value(metric, float(value.value), value.unit)
        metric_observations[metric].append((object_id, observation, normalized))

    symptom_events = by_domain[DailyDomain.SYMPTOMS]
    result.append(
        _summary(
            DailyDomain.SYMPTOMS,
            MetricKey.SYMPTOM_EPISODE_COUNT,
            [1.0] * len(symptom_events),
            len(symptom_events),
            "count-reported-events-v1",
        )
    )

    symptom_rows = metric_observations[MetricKey.SYMPTOM_SEVERITY]
    symptom_rows.sort(key=lambda row: _observation_order(row[1], local_date, timezone, row[0]))
    result.append(
        _summary(
            DailyDomain.SYMPTOMS,
            MetricKey.SYMPTOM_SEVERITY,
            [row[2] for row in symptom_rows[-1:]],
            len(symptom_rows),
            "latest-observation-v1",
            latest=True,
        )
    )

    for metric in (
        MetricKey.WEIGHT,
        MetricKey.TEMPERATURE,
        MetricKey.SYSTOLIC_PRESSURE,
        MetricKey.DIASTOLIC_PRESSURE,
        MetricKey.PULSE,
    ):
        rows = metric_observations[metric]
        rows.sort(key=lambda row: _observation_order(row[1], local_date, timezone, row[0]))
        result.append(
            _summary(
                DailyDomain.MEASUREMENTS,
                metric,
                [row[2] for row in rows[-1:]],
                len(rows),
                "latest-observation-v1",
                latest=True,
            )
        )
    return result
