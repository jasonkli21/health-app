"""Versioned sparse summaries over validated Event and Observation schemas."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from itertools import pairwise
from math import fsum, isfinite
from typing import Annotated, Any
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
    CustomTrackerValueV1,
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


@dataclass(frozen=True)
class DailyProvenance:
    """Minimal source details needed to select safe daily representatives."""

    source_kind: str | None = None
    confirmation_status: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    revision: int = 1


def _healthkit_aggregate_selection(
    rows: list[tuple[UUID, ObservationSchemaV1]],
    provenance: Mapping[UUID, DailyProvenance],
    preferred_installations: Mapping[str, UUID],
) -> set[UUID]:
    """Choose one permitted imported aggregate per metric/day/window."""
    selected: set[UUID] = set()
    for resource_type, metric in (
        ("steps", MetricKey.STEPS),
        ("heart_rate_summary", MetricKey.HEART_RATE_SUMMARY),
    ):
        candidates: list[tuple[UUID, ObservationSchemaV1, DailyProvenance]] = []
        for object_id, observation in rows:
            source = provenance.get(object_id)
            if (
                source is not None
                and source.metadata.get("healthkit_resource_type") == resource_type
                and observation.payload.value.metric == metric
            ):
                candidates.append((object_id, observation, source))
        if not candidates:
            continue

        by_day: dict[date, list[tuple[UUID, ObservationSchemaV1, DailyProvenance]]] = defaultdict(
            list
        )
        for row in candidates:
            if isinstance(row[1].time, DateOnlyTimePoint):
                by_day[row[1].time.local_date].append(row)

        day_representatives: list[tuple[UUID, ObservationSchemaV1, DailyProvenance]] = []
        for variants in by_day.values():
            corrections = [
                row
                for row in variants
                if row[2].source_kind == "manual" and row[2].confirmation_status == "user_confirmed"
            ]
            if corrections:
                # A deliberate edit to an imported aggregate remains the one
                # analytical value for its local day, independent of device choice.
                winner = max(corrections, key=lambda row: (row[2].revision, str(row[0])))
            else:
                preferred = preferred_installations.get(resource_type)
                eligible = (
                    [
                        row
                        for row in variants
                        if row[2].metadata.get("healthkit_device_installation_id") == str(preferred)
                    ]
                    if preferred is not None
                    else []
                )
                if not eligible:
                    continue
                winner = min(
                    eligible,
                    key=lambda row: (
                        -int(row[2].metadata.get("healthkit_source_revision", 0)),
                        row[1].time.timezone if isinstance(row[1].time, DateOnlyTimePoint) else "",
                        str(row[0]),
                    ),
                )
            day_representatives.append(winner)

        if resource_type == "heart_rate_summary":
            # A daily summary is indivisible. If timezone changes produced
            # overlapping windows, keep the newest whole window and omit the
            # overlapping older summary instead of adding both.
            ranked = sorted(
                day_representatives,
                key=lambda row: (
                    -int(row[2].metadata.get("healthkit_source_revision", 0)),
                    str(row[2].metadata.get("healthkit_coverage_start", "")),
                    str(row[0]),
                ),
            )
            accepted_windows: list[tuple[datetime, datetime]] = []
            for object_id, _, source in ranked:
                start_raw = source.metadata.get("healthkit_coverage_start")
                end_raw = source.metadata.get("healthkit_coverage_end")
                if not isinstance(start_raw, str) or not isinstance(end_raw, str):
                    # Non-HealthKit observations do not enter this candidate
                    # set; imported summaries require validated coverage.
                    continue
                try:
                    start = datetime.fromisoformat(start_raw)
                    end = datetime.fromisoformat(end_raw)
                except ValueError:
                    continue
                if any(
                    start < existing_end and end > existing_start
                    for existing_start, existing_end in accepted_windows
                ):
                    continue
                accepted_windows.append((start, end))
                selected.add(object_id)
        else:
            selected.update(row[0] for row in day_representatives)
    return selected


def _sleep_duration_minutes(
    rows: list[tuple[UUID, EventSchemaV1]],
    provenance: Mapping[UUID, DailyProvenance],
    day_start: datetime,
    day_end: datetime,
) -> float | None:
    intervals: list[tuple[UUID, datetime, datetime, str | None, DailyProvenance | None]] = []
    boundaries: set[datetime] = set()
    for object_id, event in rows:
        if event.ended_at is None or not isinstance(event.time, InstantTimePoint):
            continue
        start = max(event.time.occurred_at.astimezone(UTC), day_start)
        end = min(event.ended_at.astimezone(UTC), day_end)
        if start >= end:
            continue
        source = provenance.get(object_id)
        stage = source.metadata.get("healthkit_sleep_stage") if source is not None else None
        intervals.append((object_id, start, end, stage if isinstance(stage, str) else None, source))
        boundaries.update((start, end))
    if not intervals:
        return None

    asleep_seconds = 0.0
    points = sorted(boundaries)
    for start, end in pairwise(points):
        active = [row for row in intervals if row[1] < end and row[2] > start]
        if not active:
            continue
        staged = [row for row in active if row[3] in {"awake", "core", "deep", "rem"}]
        choices = staged or active
        choices.sort(
            key=lambda row: (
                0
                if row[4] is not None
                and row[4].source_kind == "manual"
                and row[4].confirmation_status == "user_confirmed"
                else 1,
                str(
                    (row[4].metadata if row[4] else {}).get(
                        "healthkit_source_bundle_identifier", ""
                    )
                ),
                str(row[0]),
            )
        )
        stage = choices[0][3]
        if stage != "awake":
            asleep_seconds += (end - start).total_seconds()
    return asleep_seconds / 60.0


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
    provenance: DailyProvenance | None = None,
) -> tuple[date, int, datetime, int, str]:
    """Order by observed calendar date, then exact instant when one was supplied, then ID."""
    if isinstance(observation.time, DateOnlyTimePoint):
        return observation.time.local_date, 0, datetime.min.replace(tzinfo=UTC), 0, str(object_id)
    instant = observation.time.occurred_at.astimezone(ZoneInfo(timezone))
    manual_confirmed = (
        provenance is not None
        and provenance.source_kind == "manual"
        and provenance.confirmation_status == "user_confirmed"
    )
    return instant.date(), 1, instant.astimezone(UTC), int(manual_confirmed), str(object_id)


def _summary(
    domain: DailyDomain,
    metric: MetricKey,
    values: list[float],
    logged_count: int,
    method: str,
    *,
    latest: bool = False,
    coverage_counts: tuple[int, int] | None = None,
) -> MetricSummaryV1:
    known_count = (
        coverage_counts[0]
        if coverage_counts is not None
        else logged_count
        if latest and values
        else len(values)
    )
    total_count = coverage_counts[1] if coverage_counts is not None else logged_count
    if values:
        if latest:
            known_value = values[-1]
        else:
            try:
                known_value = fsum(values)
            except (OverflowError, ValueError) as exc:
                raise ValueError("daily summary exceeds the safe numeric range") from exc
            if not isfinite(known_value):
                raise ValueError("daily summary exceeds the safe numeric range")
    else:
        known_value = None
    return MetricSummaryV1(
        domain=domain,
        metric=metric,
        known_value=known_value,
        unit=canonical_unit(metric).value,
        logged_count=logged_count,
        coverage=CoverageV1(known_count=known_count, total_count=total_count),
        method_version=f"{TODAY_METHOD_VERSION}/{method}/{UNIT_CONVERSION_VERSION}",
        partial=total_count > 0 and known_count < total_count,
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
    *,
    provenance: Mapping[UUID, DailyProvenance] | None = None,
    preferred_installations: Mapping[str, UUID] | None = None,
) -> list[MetricSummaryV1]:
    """Compute fixed metric summaries; absent values stay null and explicit zero stays zero."""
    source_info = provenance or {}
    preferred = preferred_installations or {}
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
    sleep_minutes = _sleep_duration_minutes(
        [
            (object_id, event)
            for object_id, event in day_events
            if event.domain == DailyDomain.SLEEP
        ],
        source_info,
        day_start,
        day_end,
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
                [sleep_minutes] if sleep_minutes is not None else [],
                len(by_domain[DailyDomain.SLEEP]),
                "sleep-segment-selected-v1",
            ),
        ]
    )

    metric_observations: dict[MetricKey, list[tuple[UUID, ObservationSchemaV1, float]]] = (
        defaultdict(list)
    )
    for object_id, observation in day_observations:
        value = observation.payload.value
        if isinstance(value, CustomTrackerValueV1):
            continue
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
    symptom_rows.sort(
        key=lambda row: _observation_order(
            row[1], local_date, timezone, row[0], source_info.get(row[0])
        )
    )
    result.append(
        _summary(
            DailyDomain.SYMPTOMS,
            MetricKey.SYMPTOM_SEVERITY,
            [row[2] for row in symptom_rows[-1:]],
            len(symptom_events),
            "latest-linked-episode-v2",
            latest=True,
            coverage_counts=(len(symptom_rows), len(symptom_events)),
        )
    )

    aggregate_rows = [
        (object_id, observation)
        for object_id, observation in observations
        if observation.payload.value.metric in (MetricKey.STEPS, MetricKey.HEART_RATE_SUMMARY)
    ]
    selected_aggregates = _healthkit_aggregate_selection(
        aggregate_rows,
        source_info,
        preferred,
    )
    step_rows = [
        row
        for row in metric_observations[MetricKey.STEPS]
        if source_info.get(row[0], DailyProvenance()).metadata.get("healthkit_resource_type")
        != "steps"
        or row[0] in selected_aggregates
    ]
    result.append(
        _summary(
            DailyDomain.EXERCISE,
            MetricKey.STEPS,
            [row[2] for row in step_rows],
            len(step_rows),
            "sum-selected-device-day-v1",
        )
    )

    for metric in (
        MetricKey.WEIGHT,
        MetricKey.TEMPERATURE,
        MetricKey.SYSTOLIC_PRESSURE,
        MetricKey.DIASTOLIC_PRESSURE,
        MetricKey.PULSE,
        MetricKey.RESTING_HEART_RATE,
        MetricKey.HEART_RATE_SUMMARY,
    ):
        rows = metric_observations[metric]
        if metric == MetricKey.HEART_RATE_SUMMARY:
            rows = [
                row
                for row in rows
                if source_info.get(row[0], DailyProvenance()).metadata.get(
                    "healthkit_resource_type"
                )
                != "heart_rate_summary"
                or row[0] in selected_aggregates
            ]
        rows.sort(
            key=lambda row: _observation_order(
                row[1], local_date, timezone, row[0], source_info.get(row[0])
            )
        )
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
