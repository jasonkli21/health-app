from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from health_api.application.analytics_service import (
    _snapshot,
    _standard_points,
    _tracker_metric_label,
)
from health_api.domain.analytics import (
    ASSOCIATION_PAIRS,
    METRIC_CATALOG,
    AnalyticsMetric,
    DailyMetricPoint,
    ExperimentPayloadV1,
    build_association_result,
    build_trend_result,
    spearman_rho,
)
from health_api.domain.schemas import EventSchemaV1, ObservationSchemaV1


def test_analytics_revision_snapshot_is_json_serializable() -> None:
    now = datetime(2026, 10, 7, 12, 30, tzinfo=UTC)
    obj = SimpleNamespace(
        id=uuid4(),
        object_type="derived_signal",
        domain="analytics",
        status="active",
        title="Weight trend",
        valid_from=now,
        valid_to=None,
        recorded_at=now,
        created_at=now,
        updated_at=now,
        source_id=uuid4(),
        confirmation_status="unconfirmed",
        schema_version=1,
        revision=1,
        notes=None,
        metadata_json={},
        ai_use_allowed=False,
        cross_domain_use_allowed=False,
    )
    artifact = SimpleNamespace(
        artifact_kind="derived_signal",
        state="current",
        scope_key="a" * 64,
        dedupe_key="b" * 64,
        payload={"state": "current", "result": {"from_date": "2026-10-01"}},
    )

    snapshot = _snapshot(obj, artifact)  # type: ignore[arg-type]
    encoded = json.dumps(snapshot)

    assert str(obj.id) in encoded
    assert now.isoformat() in encoded


def _symptom_event(at: datetime) -> EventSchemaV1:
    return EventSchemaV1.model_validate(
        {
            "domain": "symptoms",
            "time": {"precision": "instant", "occurred_at": at, "timezone": "UTC"},
            "payload": {"kind": "symptom", "label": "Headache"},
        }
    )


def _severity(at: datetime, value: int) -> ObservationSchemaV1:
    return ObservationSchemaV1.model_validate(
        {
            "domain": "symptoms",
            "time": {"precision": "instant", "occurred_at": at, "timezone": "UTC"},
            "payload": {"value": {"metric": "symptom_severity", "value": value}},
        }
    )


def test_analytics_symptom_severity_uses_latest_linked_same_day_value() -> None:
    day = date(2026, 10, 7)
    first_event_id, latest_event_id = uuid4(), uuid4()
    first_severity_id, latest_severity_id = uuid4(), uuid4()
    first_at = datetime(2026, 10, 7, 9, tzinfo=UTC)
    latest_at = datetime(2026, 10, 7, 15, tzinfo=UTC)
    events = [
        (
            SimpleNamespace(id=first_event_id, revision=1),
            SimpleNamespace(),
            _symptom_event(first_at),
        ),
        (
            SimpleNamespace(id=latest_event_id, revision=1),
            SimpleNamespace(),
            _symptom_event(latest_at),
        ),
    ]
    observations = [
        (
            SimpleNamespace(id=first_severity_id, revision=1),
            SimpleNamespace(),
            _severity(first_at, 4),
        ),
        (
            SimpleNamespace(id=latest_severity_id, revision=1),
            SimpleNamespace(),
            _severity(latest_at, 0),
        ),
    ]

    points, evidence = _standard_points(
        "symptom_severity",
        events,  # type: ignore[arg-type]
        observations,  # type: ignore[arg-type]
        {
            first_event_id: {first_severity_id},
            latest_event_id: {latest_severity_id},
        },
        day,
        day,
        "UTC",
    )

    assert points[0].value == 0
    assert points[0].known_count == 2
    assert {reference.object_id for reference in evidence} == {
        first_event_id,
        latest_event_id,
        first_severity_id,
        latest_severity_id,
    }


def test_analytics_symptom_severity_omits_cross_day_relationships() -> None:
    day = date(2026, 10, 7)
    event_id, observation_id = uuid4(), uuid4()
    event_at = datetime(2026, 10, 7, 23, tzinfo=UTC)
    observation_at = datetime(2026, 10, 8, 1, tzinfo=UTC)
    points, evidence = _standard_points(
        "symptom_severity",
        [(SimpleNamespace(id=event_id, revision=1), SimpleNamespace(), _symptom_event(event_at))],  # type: ignore[arg-type]
        [
            (
                SimpleNamespace(id=observation_id, revision=1),
                SimpleNamespace(),
                _severity(observation_at, 4),
            )
        ],  # type: ignore[arg-type]
        {event_id: {observation_id}},
        day,
        day,
        "UTC",
    )

    assert points[0].value is None
    assert points[0].known_count == 0
    assert all(reference.object_id != observation_id for reference in evidence)


def test_tracker_metric_labels_fit_contract_for_long_unicode_names() -> None:
    label = _tracker_metric_label("睡眠" * 60, "気分" * 60, 12)

    assert len(label) <= 80
    assert label.endswith("(schema v12)")


def test_experiment_actual_end_is_an_aware_terminal_boundary() -> None:
    payload = {
        "hypothesis": "Sleep improves energy",
        "intervention": "Keep a regular bedtime",
        "outcome_metric": "energy",
        "baseline_start": "2026-10-01",
        "start_date": "2026-10-06",
        "end_date": "2026-10-12",
        "actual_end_at": "2026-10-09T23:00:00Z",
        "status": "stopped",
    }
    assert ExperimentPayloadV1.model_validate(payload).actual_end_at == datetime(
        2026, 10, 9, 23, tzinfo=UTC
    )

    with pytest.raises(ValueError, match="aware terminal boundary"):
        ExperimentPayloadV1.model_validate(
            {**payload, "actual_end_at": "2026-10-09T23:00:00", "status": "stopped"}
        )


def test_trend_golden_keeps_unknown_days_and_uses_seven_known_samples() -> None:
    start = date(2026, 1, 1)
    values = [1, 2, None, 3, 4, 5, 6, 7]
    points = [
        DailyMetricPoint(
            date=start + timedelta(days=index),
            value=value,
            logged_count=0 if value is None else 1,
            known_count=0 if value is None else 1,
            total_count=0 if value is None else 1,
            partial=False,
        )
        for index, value in enumerate(values)
    ]

    result = build_trend_result(
        "energy",
        points,
        definition=METRIC_CATALOG[AnalyticsMetric.ENERGY],
        from_date=start,
        to_date=start + timedelta(days=len(points) - 1),
        timezone="UTC",
        evidence_refs=[],
    )

    assert result.coverage.calendar_days == 8
    assert result.coverage.known_days == 7
    assert result.coverage.missing_days == 1
    assert result.mean == 4.0
    assert result.median == 4.0
    assert len(result.rolling_7_known_day_mean) == 1
    assert result.rolling_7_known_day_mean[0].mean == 4.0
    assert result.rolling_7_known_day_mean[0].date == start + timedelta(days=7)


def test_trend_golden_compares_calendar_halves_and_handles_zero_baseline() -> None:
    start = date(2026, 1, 1)

    def result_for(before: float):
        points = [
            DailyMetricPoint(
                date=start + timedelta(days=index),
                value=before if index < 5 else 2.0,
                logged_count=1,
                known_count=1,
                total_count=1,
                partial=False,
            )
            for index in range(10)
        ]
        return build_trend_result(
            "energy",
            points,
            definition=METRIC_CATALOG[AnalyticsMetric.ENERGY],
            from_date=start,
            to_date=start + timedelta(days=9),
            timezone="UTC",
            evidence_refs=[],
        )

    ordinary = result_for(1.0).comparison
    assert ordinary is not None
    assert ordinary.before.mean == 1.0
    assert ordinary.after.mean == 2.0
    assert ordinary.mean_difference == 1.0
    assert ordinary.percent_change == 100.0

    zero_baseline = result_for(0.0).comparison
    assert zero_baseline is not None
    assert zero_baseline.mean_difference == 2.0
    assert zero_baseline.percent_change is None


def test_spearman_golden_covers_ties_constants_and_inverse_order() -> None:
    assert spearman_rho([1, 2, 2, 4], [4, 1, 3, 2]) == pytest.approx(-0.6324555320336759)
    assert spearman_rho([1, 2, 3], [9, 4, 1]) == -1.0
    assert spearman_rho([1, 1, 1], [1, 2, 3]) is None


def test_association_golden_enforces_paired_and_calendar_thresholds() -> None:
    start = date(2026, 1, 1)
    pair = ASSOCIATION_PAIRS["sleep_duration:symptom_severity"]

    def points(values: list[float | None]) -> list[DailyMetricPoint]:
        return [
            DailyMetricPoint(
                date=start + timedelta(days=index),
                value=value,
                logged_count=0 if value is None else 1,
                known_count=0 if value is None else 1,
                total_count=0 if value is None else 1,
                partial=False,
            )
            for index, value in enumerate(values)
        ]

    first = [float(index) for index in range(14)] + [None] * 7
    inverse = [float(13 - index) for index in range(14)] + [None] * 7
    available = build_association_result(
        pair,
        points(first),
        points(inverse),
        from_date=start,
        to_date=start + timedelta(days=20),
        timezone="UTC",
        evidence_refs=[],
    )
    assert available.status == "available"
    assert available.paired_days == 14
    assert available.calendar_days == 21
    assert available.rho == -1.0

    insufficient = build_association_result(
        pair,
        points(first[:13] + [None] * 8),
        points(inverse[:13] + [None] * 8),
        from_date=start,
        to_date=start + timedelta(days=20),
        timezone="UTC",
        evidence_refs=[],
    )
    assert insufficient.status == "insufficient_data"
    assert insufficient.rho is None
