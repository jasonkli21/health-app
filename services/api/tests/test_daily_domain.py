from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from health_api.domain.daily import (
    UNIT_CONVERSION_VERSION,
    convert_value,
    interval_overlap_seconds,
    local_day_bounds,
)
from health_api.domain.daily_rollups import DailyProvenance, _summary, summarize_today
from health_api.domain.schemas import (
    DailyDomain,
    EventPayloadSchemaV1,
    EventSchemaV1,
    MeasurementUnit,
    MetricKey,
    ObservationPayloadV1,
    ObservationSchemaV1,
    ProfileSchemaRegistry,
    validate_iana_timezone,
)

ROOT = Path(__file__).resolve().parent


def test_daily_schemas_are_registered_as_immutable_v1_contracts() -> None:
    assert isinstance(
        ProfileSchemaRegistry.validate(
            "event",
            1,
            {"kind": "meal", "label": "Breakfast"},
        ),
        EventPayloadSchemaV1,
    )
    assert isinstance(
        ProfileSchemaRegistry.validate(
            "observation",
            1,
            {"value": {"metric": "weight", "value": 60, "unit": "kg"}},
        ),
        ObservationPayloadV1,
    )
    with pytest.raises(ValueError, match="unsupported"):
        ProfileSchemaRegistry.validate("event", 2, {})


@pytest.mark.parametrize(
    ("metric", "value", "source", "target", "expected"),
    [
        (MetricKey.ENERGY, 100, MeasurementUnit.KJ, MeasurementUnit.KCAL, 100 / 4.184),
        (MetricKey.DURATION, 2, MeasurementUnit.HOUR, MeasurementUnit.MIN, 120),
        (MetricKey.DISTANCE, 1, MeasurementUnit.MI, MeasurementUnit.M, 1609.344),
        (MetricKey.WEIGHT, 150, MeasurementUnit.LB, MeasurementUnit.KG, 68.0388555),
        (MetricKey.TEMPERATURE, 98.6, MeasurementUnit.FAHRENHEIT, MeasurementUnit.CELSIUS, 37),
    ],
)
def test_unit_conversions_use_the_named_versioned_factors(
    metric: MetricKey,
    value: float,
    source: MeasurementUnit,
    target: MeasurementUnit,
    expected: float,
) -> None:
    assert UNIT_CONVERSION_VERSION == "unit-v1"
    assert convert_value(metric, value, source, target) == pytest.approx(expected)
    assert convert_value(metric, expected, target, source) == pytest.approx(value)


@pytest.mark.parametrize("value", [1.1e300, "1.1e300", "1e308"])
def test_daily_quantity_bound_applies_after_numeric_coercion(value: float | str) -> None:
    with pytest.raises(ValueError, match="safe aggregation"):
        EventSchemaV1.model_validate(
            {
                "domain": "nutrition",
                "time": {"precision": "date_only", "local_date": "2026-01-01", "timezone": "UTC"},
                "payload": {
                    "kind": "meal",
                    "label": "Meal",
                    "energy": {"value": value, "unit": "kcal"},
                },
            }
        )


def test_unit_conversion_rejects_unrelated_units_and_nonfinite_values() -> None:
    with pytest.raises(ValueError, match="not supported"):
        convert_value(MetricKey.WEIGHT, 1, MeasurementUnit.MI, MeasurementUnit.KG)
    with pytest.raises(ValueError, match="finite"):
        convert_value(MetricKey.ENERGY, float("inf"), MeasurementUnit.KCAL)
    with pytest.raises(ValueError, match="numeric range"):
        convert_value(MetricKey.DISTANCE, 1e300, MeasurementUnit.MI)
    with pytest.raises(ValueError, match="safe aggregation"):
        EventSchemaV1.model_validate(
            {
                "domain": "nutrition",
                "time": {"precision": "date_only", "local_date": "2026-01-01", "timezone": "UTC"},
                "payload": {
                    "kind": "meal",
                    "label": "Meal",
                    "energy": {"value": 1.1e300, "unit": "kcal"},
                },
            }
        )
    with pytest.raises(ValueError, match="after unit conversion"):
        EventSchemaV1.model_validate(
            {
                "domain": "exercise",
                "time": {
                    "precision": "date_only",
                    "local_date": "2026-01-01",
                    "timezone": "UTC",
                },
                "payload": {
                    "kind": "workout",
                    "label": "Walk",
                    "duration": {"value": 1e300, "unit": "h"},
                },
            }
        )
    with pytest.raises(ValueError, match="after unit conversion"):
        EventSchemaV1.model_validate(
            {
                "domain": "exercise",
                "time": {
                    "precision": "date_only",
                    "local_date": "2026-01-01",
                    "timezone": "UTC",
                },
                "payload": {
                    "kind": "workout",
                    "label": "Walk",
                    "distance": {"value": 1e300, "unit": "mi"},
                },
            }
        )
    with pytest.raises(ValueError, match="safe numeric range"):
        _summary(DailyDomain.NUTRITION, MetricKey.ENERGY, [1e308, 1e308], 2, "sum-known-v1")


@pytest.mark.parametrize(
    ("local_date", "expected_hours"),
    [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)],
)
def test_local_day_bounds_follow_daylight_saving_transitions(
    local_date: date, expected_hours: int
) -> None:
    start, end = local_day_bounds(local_date, "America/Los_Angeles")
    assert (end - start).total_seconds() == expected_hours * 3600
    assert start.tzinfo == UTC and end.tzinfo == UTC


def test_interval_overlap_is_half_open_and_elapsed_time_based() -> None:
    start, end = local_day_bounds(date(2026, 11, 1), "America/Los_Angeles")
    assert (
        interval_overlap_seconds(
            datetime(2026, 11, 1, 5, tzinfo=UTC),
            datetime(2026, 11, 1, 15, tzinfo=UTC),
            start,
            end,
        )
        == 8 * 3600
    )
    assert (
        interval_overlap_seconds(
            end,
            datetime(2026, 11, 2, 9, tzinfo=UTC),
            start,
            end,
        )
        == 0
    )


def test_timezone_validation_rejects_unknown_zone() -> None:
    with pytest.raises(ValueError, match="IANA"):
        validate_iana_timezone("Mars/Olympus")


@pytest.mark.parametrize(
    "payload",
    [
        {
            "domain": "nutrition",
            "time": {
                "precision": "instant",
                "occurred_at": "2026-01-01T12:00:00Z",
                "timezone": "UTC",
            },
            "payload": {"kind": "meal", "label": "Lunch", "severity": 4},
        },
        {
            "domain": "exercise",
            "time": {
                "precision": "instant",
                "occurred_at": "2026-01-01T12:00:00Z",
                "timezone": "UTC",
            },
            "ended_at": "2026-01-01T13:00:00Z",
            "payload": {
                "kind": "workout",
                "label": "Walk",
                "duration": {"value": 60, "unit": "min"},
            },
        },
    ],
)
def test_events_reject_double_metric_carriers_and_unlinked_symptom_severity(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        EventSchemaV1.model_validate(payload)


def test_observation_metric_requires_compatible_unit_and_local_time() -> None:
    base = {
        "domain": "measurements",
        "time": {
            "precision": "instant",
            "occurred_at": "2026-01-01T12:00:00Z",
            "timezone": "UTC",
        },
        "payload": {"value": {"metric": "weight", "value": 70, "unit": "mmHg"}},
    }
    with pytest.raises(ValidationError, match="unit"):
        ObservationSchemaV1.model_validate(base)
    assert ObservationSchemaV1.model_validate(
        {
            "domain": "measurements",
            "time": {
                "precision": "date_only",
                "local_date": "2026-01-01",
                "timezone": "UTC",
            },
            "payload": {"value": {"metric": "weight", "value": 70, "unit": "kg"}},
        }
    ).time.model_dump() == {
        "precision": "date_only",
        "local_date": date(2026, 1, 1),
        "timezone": "UTC",
    }


def test_rollup_golden_fixture_preserves_zero_sparse_coverage_and_dst_overlap() -> None:
    fixture = json.loads((ROOT / "fixtures" / "daily-rollups.json").read_text())
    events = [
        (UUID(item["id"]), EventSchemaV1.model_validate(item["entry"]))
        for item in fixture["events"]
    ]
    observations = [
        (UUID(item["id"]), ObservationSchemaV1.model_validate(item["entry"]))
        for item in fixture["observations"]
    ]
    summaries = summarize_today(
        events,
        observations,
        date.fromisoformat(fixture["date"]),
        fixture["timezone"],
    )

    by_key = {f"{item.domain.value}/{item.metric.value}": item for item in summaries}
    assert set(fixture["expected"]).issubset(by_key)
    for key, expected in fixture["expected"].items():
        actual = by_key[key]
        assert actual.known_value == pytest.approx(expected["known_value"])
        assert actual.unit == expected["unit"]
        assert actual.logged_count == expected["logged_count"]
        assert actual.coverage.known_count == expected["known_count"]
        assert actual.coverage.total_count == expected["total_count"]
        assert actual.partial is expected["partial"]
        assert actual.method_version == expected["method_version"]

    nutrition = by_key["nutrition/energy"]
    assert nutrition.known_value == 0
    assert nutrition.partial
    assert by_key["exercise/duration"].known_value == 90
    assert by_key["sleep/duration"].known_value == 480
    assert by_key["measurements/temperature"].known_value == pytest.approx(37)
    assert by_key["measurements/systolic_pressure"].known_value is None
    assert by_key["measurements/systolic_pressure"].logged_count == 0


def test_cross_day_workout_allocates_duration_but_assigns_distance_to_start_day() -> None:
    event = EventSchemaV1.model_validate(
        {
            "domain": "exercise",
            "time": {
                "precision": "instant",
                "occurred_at": "2026-01-01T23:30:00Z",
                "timezone": "UTC",
            },
            "ended_at": "2026-01-02T00:30:00Z",
            "payload": {
                "kind": "workout",
                "label": "Walk",
                "distance": {"value": 2, "unit": "km"},
            },
        }
    )
    summaries = summarize_today(
        [(UUID("00000000-0000-0000-0000-000000000020"), event)],
        [],
        date(2026, 1, 2),
        "UTC",
    )
    by_key = {(summary.domain, summary.metric): summary for summary in summaries}
    duration = by_key[(DailyDomain.EXERCISE, MetricKey.DURATION)]
    distance = by_key[(DailyDomain.EXERCISE, MetricKey.DISTANCE)]
    assert duration.known_value == 30
    assert distance.known_value is None
    assert distance.logged_count == 1
    assert distance.partial


def test_date_only_is_assigned_by_local_date_without_a_fake_instant() -> None:
    point = {
        "precision": "date_only",
        "local_date": "2026-01-01",
        "timezone": "UTC",
    }
    event = EventSchemaV1.model_validate(
        {"domain": "nutrition", "time": point, "payload": {"kind": "meal", "label": "Meal"}}
    )
    assert event.time.model_dump(mode="json") == point
    assert not hasattr(event.time, "occurred_at")


def test_sleep_can_be_logged_without_inventing_an_end_or_duration() -> None:
    date_only = EventSchemaV1.model_validate(
        {
            "domain": "sleep",
            "time": {"precision": "date_only", "local_date": "2026-01-01", "timezone": "UTC"},
            "payload": {"kind": "sleep", "quality": 3},
        }
    )
    known_start = EventSchemaV1.model_validate(
        {
            "domain": "sleep",
            "time": {
                "precision": "instant",
                "occurred_at": "2026-01-01T22:00:00Z",
                "timezone": "UTC",
            },
            "payload": {"kind": "sleep"},
        }
    )
    summaries = summarize_today(
        [(UUID(int=1), date_only), (UUID(int=2), known_start)],
        [],
        date(2026, 1, 1),
        "UTC",
    )
    duration = next(
        row
        for row in summaries
        if row.metric == MetricKey.DURATION and row.domain == DailyDomain.SLEEP
    )
    assert duration.known_value is None
    assert duration.logged_count == 2
    assert duration.coverage.known_count == 0
    assert duration.coverage.total_count == 2
    assert duration.partial


def test_symptom_severity_coverage_uses_all_logged_episodes() -> None:
    events = []
    for identity, label in ((20, "Headache"), (21, "Nausea")):
        events.append(
            (
                UUID(int=identity),
                EventSchemaV1.model_validate(
                    {
                        "domain": "symptoms",
                        "time": {
                            "precision": "instant",
                            "occurred_at": "2026-01-01T12:00:00Z",
                            "timezone": "UTC",
                        },
                        "payload": {"kind": "symptom", "label": label},
                    }
                ),
            )
        )
    severity = ObservationSchemaV1.model_validate(
        {
            "domain": "symptoms",
            "time": {
                "precision": "instant",
                "occurred_at": "2026-01-01T12:00:00Z",
                "timezone": "UTC",
            },
            "payload": {"value": {"metric": "symptom_severity", "value": 4}},
        }
    )
    summary = next(
        row
        for row in summarize_today(events, [(UUID(int=22), severity)], date(2026, 1, 1), "UTC")
        if row.metric == MetricKey.SYMPTOM_SEVERITY
    )
    assert summary.known_value == 4
    assert summary.logged_count == 2
    assert summary.coverage.known_count == 1
    assert summary.coverage.total_count == 2
    assert summary.partial


def test_sleep_rollup_excludes_awake_and_counts_overlapping_sources_once() -> None:
    object_ids = [UUID(int=value) for value in (31, 32, 33, 34)]
    intervals = [
        ("2026-10-01T07:00:00Z", "2026-10-01T10:00:00Z", "asleep"),
        ("2026-10-01T07:00:00Z", "2026-10-01T08:00:00Z", "core"),
        ("2026-10-01T08:00:00Z", "2026-10-01T08:30:00Z", "awake"),
        ("2026-10-01T08:30:00Z", "2026-10-01T09:00:00Z", "rem"),
    ]
    events = [
        (
            object_id,
            EventSchemaV1.model_validate(
                {
                    "domain": "sleep",
                    "time": {
                        "precision": "instant",
                        "occurred_at": start,
                        "timezone": "UTC",
                    },
                    "ended_at": end,
                    "payload": {"kind": "sleep"},
                }
            ),
        )
        for object_id, (start, end, _) in zip(object_ids, intervals, strict=True)
    ]
    provenance = {
        object_id: DailyProvenance(
            source_kind="device",
            confirmation_status="unconfirmed",
            metadata={"healthkit_sleep_stage": stage},
        )
        for object_id, (_, _, stage) in zip(object_ids, intervals, strict=True)
    }
    duration = next(
        row
        for row in summarize_today(events, [], date(2026, 10, 1), "UTC", provenance=provenance)
        if row.domain == DailyDomain.SLEEP and row.metric == MetricKey.DURATION
    )
    # Detailed stages replace the generic interval where they overlap; the
    # generic source supplies the final uncovered hour without double-counting.
    assert duration.known_value == 150
    assert duration.method_version == "today-v1/sleep-segment-selected-v1/unit-v1"


def test_sleep_rollup_handles_awake_only_and_cross_midnight_fall_back() -> None:
    awake = EventSchemaV1.model_validate(
        {
            "domain": "sleep",
            "time": {
                "precision": "instant",
                "occurred_at": "2026-11-01T08:00:00Z",
                "timezone": "America/Los_Angeles",
            },
            "ended_at": "2026-11-01T09:00:00Z",
            "payload": {"kind": "sleep"},
        }
    )
    overnight = EventSchemaV1.model_validate(
        {
            "domain": "sleep",
            "time": {
                "precision": "instant",
                "occurred_at": "2026-11-01T06:30:00Z",
                "timezone": "America/Los_Angeles",
            },
            "ended_at": "2026-11-01T09:30:00Z",
            "payload": {"kind": "sleep"},
        }
    )
    awake_summary = next(
        row
        for row in summarize_today(
            [(UUID(int=41), awake)],
            [],
            date(2026, 11, 1),
            "America/Los_Angeles",
            provenance={UUID(int=41): DailyProvenance(metadata={"healthkit_sleep_stage": "awake"})},
        )
        if row.domain == DailyDomain.SLEEP and row.metric == MetricKey.DURATION
    )
    overnight_summary = next(
        row
        for row in summarize_today(
            [(UUID(int=42), overnight)], [], date(2026, 11, 1), "America/Los_Angeles"
        )
        if row.domain == DailyDomain.SLEEP and row.metric == MetricKey.DURATION
    )
    assert awake_summary.known_value == 0
    assert overnight_summary.known_value == 150


def test_manual_confirmed_measurement_wins_only_an_equal_instant_tie() -> None:
    manual_id, imported_id, later_id = UUID(int=1), UUID(int=2), UUID(int=3)
    manual = ObservationSchemaV1.model_validate(
        {
            "domain": "measurements",
            "time": {
                "precision": "instant",
                "occurred_at": "2026-01-01T12:00:00+00:00",
                "timezone": "UTC",
            },
            "payload": {"value": {"metric": "weight", "value": 70, "unit": "kg"}},
        }
    )
    imported = ObservationSchemaV1.model_validate(
        {
            "domain": "measurements",
            "time": {
                "precision": "instant",
                "occurred_at": "2026-01-01T07:00:00-05:00",
                "timezone": "America/New_York",
            },
            "payload": {"value": {"metric": "weight", "value": 176.37, "unit": "lb"}},
        }
    )
    later = ObservationSchemaV1.model_validate(
        {
            "domain": "measurements",
            "time": {
                "precision": "instant",
                "occurred_at": "2026-01-01T13:00:00Z",
                "timezone": "UTC",
            },
            "payload": {"value": {"metric": "weight", "value": 80, "unit": "kg"}},
        }
    )
    provenance = {
        manual_id: DailyProvenance("manual", "user_confirmed"),
        imported_id: DailyProvenance("device", "unconfirmed"),
        later_id: DailyProvenance("device", "unconfirmed"),
    }
    for order in (
        [(manual_id, manual), (imported_id, imported)],
        [(imported_id, imported), (manual_id, manual)],
    ):
        summary = next(
            row
            for row in summarize_today([], order, date(2026, 1, 1), "UTC", provenance=provenance)
            if row.metric == MetricKey.WEIGHT
        )
        assert summary.known_value == 70
    later_summary = next(
        row
        for row in summarize_today(
            [],
            [(manual_id, manual), (imported_id, imported), (later_id, later)],
            date(2026, 1, 1),
            "UTC",
            provenance=provenance,
        )
        if row.metric == MetricKey.WEIGHT
    )
    assert later_summary.known_value == 80


def test_step_aggregate_representative_uses_preference_revision_and_correction() -> None:
    preferred = UUID(int=51)
    other_installation = UUID(int=52)

    def steps(identity: int, installation: UUID, timezone: str, value: int, revision: int):
        return (
            UUID(int=identity),
            ObservationSchemaV1.model_validate(
                {
                    "domain": "exercise",
                    "time": {
                        "precision": "date_only",
                        "local_date": "2026-10-01",
                        "timezone": timezone,
                    },
                    "payload": {"value": {"metric": "steps", "value": value, "unit": "steps"}},
                }
            ),
            DailyProvenance(
                "device",
                "unconfirmed",
                {
                    "healthkit_resource_type": "steps",
                    "healthkit_device_installation_id": str(installation),
                    "healthkit_source_revision": revision,
                },
            ),
        )

    first = steps(61, preferred, "America/Los_Angeles", 8000, 1)
    alias = steps(62, preferred, "US/Pacific", 9000, 2)
    unselected = steps(63, other_installation, "UTC", 12000, 9)
    observations = [(row[0], row[1]) for row in (first, alias, unselected)]
    provenance = {row[0]: row[2] for row in (first, alias, unselected)}
    summary = next(
        row
        for row in summarize_today(
            [],
            observations,
            date(2026, 10, 1),
            "UTC",
            provenance=provenance,
            preferred_installations={"steps": preferred},
        )
        if row.metric == MetricKey.STEPS
    )
    assert summary.known_value == 9000
    no_preference = next(
        row
        for row in summarize_today(
            [], observations, date(2026, 10, 1), "UTC", provenance=provenance
        )
        if row.metric == MetricKey.STEPS
    )
    assert no_preference.known_value is None
    corrected = DailyProvenance("manual", "user_confirmed", alias[2].metadata, revision=2)
    corrected_summary = next(
        row
        for row in summarize_today(
            [],
            observations,
            date(2026, 10, 1),
            "UTC",
            provenance={**provenance, alias[0]: corrected},
            preferred_installations={"steps": other_installation},
        )
        if row.metric == MetricKey.STEPS
    )
    assert corrected_summary.known_value == 9000


def test_observation_steps_are_bounded_and_date_only() -> None:
    body = {
        "domain": "exercise",
        "time": {"precision": "date_only", "local_date": "2026-01-01", "timezone": "UTC"},
        "payload": {"value": {"metric": "steps", "value": 0, "unit": "steps"}},
    }
    assert ObservationSchemaV1.model_validate(body).payload.value.value == 0  # type: ignore[union-attr]
    boundary = {
        **body,
        "payload": {"value": {"metric": "steps", "value": 10**300, "unit": "steps"}},
    }
    assert ObservationSchemaV1.model_validate(boundary).payload.value.value == 10**300  # type: ignore[union-attr]
    with pytest.raises(ValidationError):
        ObservationSchemaV1.model_validate(
            {
                **body,
                "time": {
                    "precision": "instant",
                    "occurred_at": "2026-01-01T12:00:00Z",
                    "timezone": "UTC",
                },
            }
        )
    with pytest.raises(ValidationError):
        ObservationSchemaV1.model_validate(
            {
                **body,
                "payload": {"value": {"metric": "steps", "value": 10**301, "unit": "steps"}},
            }
        )


def test_overlapping_heart_rate_windows_select_newest_complete_window() -> None:
    installation = UUID(int=71)

    def summary(identity: int, local_date: str, value: float, revision: int, start: str, end: str):
        object_id = UUID(int=identity)
        observation = ObservationSchemaV1.model_validate(
            {
                "domain": "measurements",
                "time": {"precision": "date_only", "local_date": local_date, "timezone": "UTC"},
                "payload": {
                    "value": {"metric": "heart_rate_summary", "value": value, "unit": "bpm"}
                },
            }
        )
        return (
            object_id,
            observation,
            DailyProvenance(
                "device",
                "unconfirmed",
                {
                    "healthkit_resource_type": "heart_rate_summary",
                    "healthkit_device_installation_id": str(installation),
                    "healthkit_source_revision": revision,
                    "healthkit_coverage_start": start,
                    "healthkit_coverage_end": end,
                },
            ),
        )

    older = summary(
        72, "2026-10-01", 70, 1, "2026-10-01T08:00:00+00:00", "2026-10-01T10:00:00+00:00"
    )
    newer = summary(
        73, "2026-10-02", 80, 2, "2026-10-01T09:30:00+00:00", "2026-10-01T11:00:00+00:00"
    )
    all_observations = [(older[0], older[1]), (newer[0], newer[1])]
    provenance = {older[0]: older[2], newer[0]: newer[2]}
    old_day = next(
        row
        for row in summarize_today(
            [],
            all_observations,
            date(2026, 10, 1),
            "UTC",
            provenance=provenance,
            preferred_installations={"heart_rate_summary": installation},
        )
        if row.metric == MetricKey.HEART_RATE_SUMMARY
    )
    new_day = next(
        row
        for row in summarize_today(
            [],
            all_observations,
            date(2026, 10, 2),
            "UTC",
            provenance=provenance,
            preferred_installations={"heart_rate_summary": installation},
        )
        if row.metric == MetricKey.HEART_RATE_SUMMARY
    )
    assert old_day.known_value is None
    assert new_day.known_value == 80
