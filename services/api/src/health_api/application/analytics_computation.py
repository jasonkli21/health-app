"""Pure deterministic analytics calculations over an owner-scoped input snapshot."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from health_api.application.analytics_contracts import (
    AnalyticsSourceSnapshot,
    AnalyticsValidationError,
    EventInput,
    MetricSeries,
    ObservationInput,
)
from health_api.domain.analytics import (
    DailyMetricPoint,
    EvidenceReference,
    MetricDefinition,
)
from health_api.domain.daily import local_day_bounds
from health_api.domain.daily_rollups import DailyProvenance, summarize_today
from health_api.domain.schemas import (
    CustomTrackerValueV1,
    DailyDomain,
    EventSchemaV1,
    MetricKey,
    ObservationSchemaV1,
)

_TRACKER_METRIC = re.compile(
    r"^tracker:([0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}):"
    r"([a-z][a-z0-9_]{0,31}):v([1-9][0-9]*)$"
)


_EVENT_METRICS: dict[str, tuple[DailyDomain, MetricKey]] = {
    "energy": (DailyDomain.NUTRITION, MetricKey.ENERGY),
    "exercise_duration": (DailyDomain.EXERCISE, MetricKey.DURATION),
    "exercise_distance": (DailyDomain.EXERCISE, MetricKey.DISTANCE),
    "sleep_duration": (DailyDomain.SLEEP, MetricKey.DURATION),
    "symptom_severity": (DailyDomain.SYMPTOMS, MetricKey.SYMPTOM_SEVERITY),
    "symptom_episode_count": (DailyDomain.SYMPTOMS, MetricKey.SYMPTOM_EPISODE_COUNT),
    "weight": (DailyDomain.MEASUREMENTS, MetricKey.WEIGHT),
    "temperature": (DailyDomain.MEASUREMENTS, MetricKey.TEMPERATURE),
    "systolic_pressure": (DailyDomain.MEASUREMENTS, MetricKey.SYSTOLIC_PRESSURE),
    "diastolic_pressure": (DailyDomain.MEASUREMENTS, MetricKey.DIASTOLIC_PRESSURE),
    "pulse": (DailyDomain.MEASUREMENTS, MetricKey.PULSE),
    "steps": (DailyDomain.EXERCISE, MetricKey.STEPS),
    "resting_heart_rate": (DailyDomain.MEASUREMENTS, MetricKey.RESTING_HEART_RATE),
    "heart_rate_summary": (DailyDomain.MEASUREMENTS, MetricKey.HEART_RATE_SUMMARY),
}


def _row_date_in_range(
    precision: str,
    local_date: date | None,
    instant: datetime | None,
    interval_end: datetime | None,
    start: date,
    end: date,
    timezone: str,
) -> bool:
    if precision == "date_only":
        return local_date is not None and start <= local_date <= end
    if instant is None:
        return False
    start_at = local_day_bounds(start, timezone)[0]
    if end == date.max:
        return False
    end_at = local_day_bounds(end + timedelta(days=1), timezone)[0]
    return instant < end_at and (interval_end > start_at if interval_end else instant >= start_at)


def _tracker_metric_parts(metric: str) -> tuple[UUID, str, int] | None:
    match = _TRACKER_METRIC.fullmatch(metric)
    if not match:
        return None
    try:
        return UUID(match.group(1)), match.group(2), int(match.group(3))
    except ValueError:
        return None


def _tracker_metric_label(name: str, field_label: str, version: int) -> str:
    suffix = f" (schema v{version})"
    prefix = f"{name} · {field_label}"
    max_prefix = 80 - len(suffix)
    if len(prefix) > max_prefix:
        prefix = prefix[: max_prefix - 1].rstrip() + "…"
    return prefix + suffix


def _event_metric_rows(metric: str, events: list[EventInput]) -> list[EventInput]:
    domain, _ = _EVENT_METRICS[metric]
    if metric in {"symptom_severity", "symptom_episode_count"}:
        return [row for row in events if row[2].domain == DailyDomain.SYMPTOMS]
    return [row for row in events if row[2].domain == domain]


def _observation_metric_rows(
    metric: str, observations: list[ObservationInput]
) -> list[ObservationInput]:
    _, wanted = _EVENT_METRICS[metric]
    return [row for row in observations if row[2].payload.value.metric == wanted]


def _evidence_refs(
    events: list[EventInput], observations: list[ObservationInput]
) -> list[EvidenceReference]:
    refs = [
        EvidenceReference(object_id=obj.id, revision=obj.revision, object_type="event")
        for obj, _, _ in events
    ]
    refs.extend(
        EvidenceReference(object_id=obj.id, revision=obj.revision, object_type="observation")
        for obj, _, _ in observations
    )
    return sorted(refs, key=lambda ref: (str(ref.object_id), ref.revision))


def _tracker_points(
    metric: str,
    definition: MetricDefinition,
    observations: list[ObservationInput],
    from_date: date,
    to_date: date,
    timezone: str,
) -> tuple[list[DailyMetricPoint], list[EvidenceReference]]:
    parts = _tracker_metric_parts(metric)
    if parts is None:
        raise AnalyticsValidationError("The selected metric is not supported.")
    tracker_id, field_id, version = parts
    rows = [
        row
        for row in observations
        if row[1].tracker_id == tracker_id and row[1].tracker_schema_version == version
    ]
    refs = _evidence_refs([], rows)
    points: list[DailyMetricPoint] = []
    current = from_date
    while current <= to_date:
        day_rows: list[tuple[ObservationInput, float | None]] = []
        for row in rows:
            _, item, schema = row
            if not _row_date_in_range(
                item.time_precision,
                item.local_date,
                item.observed_at,
                item.interval_end,
                current,
                current,
                timezone,
            ):
                continue
            value = schema.payload.value
            extracted: float | None = None
            if isinstance(value, CustomTrackerValueV1) and field_id in value.values:
                raw = value.values[field_id]
                if isinstance(raw, bool):
                    extracted = None
                elif isinstance(raw, (int, float)):
                    extracted = float(raw)
                elif (
                    isinstance(raw, dict)
                    and set(raw) == {"value", "unit"}
                    and raw["unit"] == definition.unit
                    and isinstance(raw["value"], (int, float))
                    and not isinstance(raw["value"], bool)
                ):
                    extracted = float(raw["value"])
            if extracted is not None:
                day_rows.append((row, extracted))
        day_rows.sort(
            key=lambda value: (
                value[0][2].time.local_date
                if value[0][2].time.precision == "date_only"
                else value[0][2].time.occurred_at.astimezone(ZoneInfo(timezone)).date(),
                0 if value[0][2].time.precision == "date_only" else 1,
                datetime.min.replace(tzinfo=UTC)
                if value[0][2].time.precision == "date_only"
                else value[0][2].time.occurred_at.astimezone(UTC),
                str(value[0][0].id),
            )
        )
        all_rows_count = sum(
            1
            for row in rows
            if _row_date_in_range(
                row[1].time_precision,
                row[1].local_date,
                row[1].observed_at,
                row[1].interval_end,
                current,
                current,
                timezone,
            )
        )
        known = len(day_rows)
        points.append(
            DailyMetricPoint(
                date=current,
                value=day_rows[-1][1] if day_rows else None,
                logged_count=all_rows_count,
                known_count=known,
                total_count=all_rows_count,
                partial=known < all_rows_count,
            )
        )
        current += timedelta(days=1)
    return points, refs


def _standard_points(
    metric: str,
    events: list[EventInput],
    observations: list[ObservationInput],
    links: dict[UUID, set[UUID]],
    from_date: date,
    to_date: date,
    timezone: str,
    provenance: dict[UUID, DailyProvenance],
    preferred_installations: dict[str, UUID],
) -> tuple[list[DailyMetricPoint], list[EvidenceReference]]:
    relevant_events = _event_metric_rows(metric, events)
    relevant_observations = _observation_metric_rows(metric, observations)
    full_events = [(obj.id, schema) for obj, _, schema in events]
    full_observations = [(obj.id, schema) for obj, _, schema in observations]

    def local_day(schema: EventSchemaV1 | ObservationSchemaV1) -> date:
        time = schema.time
        return (
            time.local_date
            if time.precision == "date_only"
            else time.occurred_at.astimezone(ZoneInfo(timezone)).date()
        )

    eligible_symptom_events = {
        object_id: local_day(schema)
        for object_id, schema in full_events
        if schema.domain == DailyDomain.SYMPTOMS and schema.payload.kind == "symptom"
    }
    observations_by_id = {object_id: schema for object_id, schema in full_observations}
    eligible_severity_ids: set[UUID] = set()
    for event_id, observation_ids in links.items():
        event_day = eligible_symptom_events.get(event_id)
        if event_day is None:
            continue
        for observation_id in observation_ids:
            observation = observations_by_id.get(observation_id)
            if (
                observation is not None
                and observation.payload.value.metric == MetricKey.SYMPTOM_SEVERITY
                and local_day(observation) == event_day
            ):
                eligible_severity_ids.add(observation_id)
    full_observations = [
        row
        for row in full_observations
        if row[1].payload.value.metric != MetricKey.SYMPTOM_SEVERITY
        or row[0] in eligible_severity_ids
    ]
    if metric == "symptom_severity":
        eligible_ids = {object_id for object_id in eligible_severity_ids}
        relevant_observations = [row for row in relevant_observations if row[0].id in eligible_ids]
    elif metric == "symptom_episode_count":
        relevant_observations = []
    refs = _evidence_refs(relevant_events, relevant_observations)
    wanted_domain, wanted_metric = _EVENT_METRICS[metric]
    points: list[DailyMetricPoint] = []
    current = from_date
    while current <= to_date:
        summaries = summarize_today(
            full_events,
            full_observations,
            current,
            timezone,
            provenance=provenance,
            preferred_installations=preferred_installations,
        )
        summary = next(
            (
                row
                for row in summaries
                if row.domain == wanted_domain and row.metric == wanted_metric
            ),
            None,
        )
        if summary is None:
            raise RuntimeError("daily metric catalog is missing a supported summary")
        points.append(
            DailyMetricPoint(
                date=current,
                value=summary.known_value,
                logged_count=summary.logged_count,
                known_count=summary.coverage.known_count,
                total_count=summary.coverage.total_count,
                partial=summary.partial,
            )
        )
        current += timedelta(days=1)
    return points, refs


def _series_from_inputs(
    metric: str,
    definition: MetricDefinition,
    from_date: date,
    to_date: date,
    timezone: str,
    generation: int,
    events: list[EventInput],
    observations: list[ObservationInput],
    links: dict[UUID, set[UUID]],
    provenance: dict[UUID, DailyProvenance],
    preferred_installations: dict[str, UUID],
) -> MetricSeries:
    if _tracker_metric_parts(metric) is not None:
        points, refs = _tracker_points(
            metric, definition, observations, from_date, to_date, timezone
        )
    else:
        points, refs = _standard_points(
            metric,
            events,
            observations,
            links,
            from_date,
            to_date,
            timezone,
            provenance,
            preferred_installations,
        )
    return definition, points, refs, generation


def _series_from_snapshot(
    metric: str,
    definition: MetricDefinition,
    from_date: date,
    to_date: date,
    timezone: str,
    snapshot: AnalyticsSourceSnapshot,
) -> MetricSeries:
    """Calculate one metric from an already loaded, typed source snapshot."""
    return _series_from_inputs(
        metric,
        definition,
        from_date,
        to_date,
        timezone,
        snapshot.generation,
        snapshot.events,
        snapshot.observations,
        snapshot.links,
        snapshot.provenance,
        snapshot.preferred_installations,
    )
