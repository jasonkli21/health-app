from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest
from health_api.application.healthkit_import_service import (
    HealthKitImportValidationError,
    _validate_entry,
)
from health_api.domain.healthkit_imports import (
    HealthKitImportBatchRequest,
    HealthKitImportEntry,
    HealthKitImportMetadata,
)
from pydantic import ValidationError

INSTALLATION_ID = UUID("4bcf0eac-f815-4a88-bb6d-d10c477b8eab")
POLICY_VERSION = "healthkit-v1"


def workout_entry(
    *, domain: str = "exercise", sample_id: str | None = None, notes: str | None = None
) -> HealthKitImportEntry:
    return HealthKitImportEntry.model_validate(
        {
            "source_sample_id": sample_id or str(uuid4()),
            "record": {
                "domain": domain,
                "time": {
                    "precision": "instant",
                    "occurred_at": "2026-10-01T16:00:00Z",
                    "timezone": "America/Los_Angeles",
                },
                "ended_at": None,
                "payload": {
                    "kind": "workout",
                    "label": "Running",
                    "duration": {"value": 30, "unit": "min"},
                    "distance": {"value": 5000, "unit": "m"},
                },
                "notes": notes,
            },
        }
    )


def test_workout_contract_requires_exercise_domain_and_no_notes() -> None:
    valid = workout_entry()
    assert _validate_entry(valid, "workouts", INSTALLATION_ID, POLICY_VERSION) == (None, None)

    with pytest.raises(ValidationError):
        workout_entry(domain="sleep")
    with pytest.raises(HealthKitImportValidationError):
        _validate_entry(
            workout_entry(notes="private note"), "workouts", INSTALLATION_ID, POLICY_VERSION
        )

    incomplete = workout_entry().model_dump(mode="python")
    incomplete["record"]["payload"]["duration"] = None
    entry = HealthKitImportEntry.model_validate(incomplete)
    with pytest.raises(HealthKitImportValidationError, match="end time or an explicit duration"):
        _validate_entry(entry, "workouts", INSTALLATION_ID, POLICY_VERSION)


@pytest.mark.parametrize(
    ("resource_type", "metric", "unit"),
    [("weight", "weight", "kg"), ("resting_heart_rate", "resting_heart_rate", "bpm")],
)
def test_low_frequency_imports_reject_intervals(resource_type: str, metric: str, unit: str) -> None:
    entry = HealthKitImportEntry.model_validate(
        {
            "source_sample_id": str(uuid4()),
            "record": {
                "domain": "measurements",
                "time": {
                    "precision": "instant",
                    "occurred_at": "2026-10-01T16:00:00Z",
                    "timezone": "UTC",
                },
                "interval_end": "2026-10-01T16:01:00Z",
                "payload": {"value": {"metric": metric, "value": 70, "unit": unit}},
            },
        }
    )
    with pytest.raises(HealthKitImportValidationError, match="exact Observation"):
        _validate_entry(entry, resource_type, INSTALLATION_ID, POLICY_VERSION)


def test_step_aggregate_requires_integer_count_and_canonical_installation_key() -> None:
    source_sample_id = f"daily:2026-10-01:America/Los_Angeles:healthkit-v1:{INSTALLATION_ID}"
    entry = HealthKitImportEntry.model_validate(
        {
            "source_sample_id": source_sample_id,
            "record": {
                "domain": "exercise",
                "time": {
                    "precision": "date_only",
                    "local_date": "2026-10-01",
                    "timezone": "America/Los_Angeles",
                },
                "interval_end": None,
                "payload": {"value": {"metric": "steps", "value": 0, "unit": "steps"}},
                "notes": None,
            },
            "metadata": {
                "aggregation_method_version": "hk-steps-source-v1",
                "source_revision": 1,
            },
        }
    )
    assert _validate_entry(entry, "steps", INSTALLATION_ID, POLICY_VERSION) == (
        date(2026, 10, 1),
        "America/Los_Angeles",
    )
    with pytest.raises(HealthKitImportValidationError):
        _validate_entry(
            entry.model_copy(update={"source_sample_id": "daily:wrong"}),
            "steps",
            INSTALLATION_ID,
            POLICY_VERSION,
        )


def test_heart_rate_summary_requires_in_day_coverage_and_mean_in_range() -> None:
    entry = HealthKitImportEntry.model_validate(
        {
            "source_sample_id": (
                f"daily:2026-10-01:America/Los_Angeles:healthkit-v1:{INSTALLATION_ID}"
            ),
            "record": {
                "domain": "measurements",
                "time": {
                    "precision": "date_only",
                    "local_date": "2026-10-01",
                    "timezone": "America/Los_Angeles",
                },
                "interval_end": None,
                "payload": {
                    "value": {
                        "metric": "heart_rate_summary",
                        "value": 71,
                        "unit": "bpm",
                    }
                },
                "notes": None,
            },
            "metadata": {
                "aggregation_method_version": "hk-heart-rate-v1",
                "source_revision": 1,
                "sample_count": 360,
                "minimum": 52,
                "maximum": 116,
                "coverage_start": "2026-10-01T08:00:00Z",
                "coverage_end": "2026-10-01T22:00:00Z",
            },
        }
    )
    assert _validate_entry(entry, "heart_rate_summary", INSTALLATION_ID, POLICY_VERSION) == (
        date(2026, 10, 1),
        "America/Los_Angeles",
    )
    invalid_body = entry.model_dump(mode="python")
    invalid_body["record"]["payload"]["value"]["value"] = 120
    invalid_mean = HealthKitImportEntry.model_validate(invalid_body)
    with pytest.raises(HealthKitImportValidationError):
        _validate_entry(invalid_mean, "heart_rate_summary", INSTALLATION_ID, POLICY_VERSION)


def test_import_contract_rejects_raw_fields_and_ambiguous_batch_ids() -> None:
    with pytest.raises(ValidationError):
        HealthKitImportMetadata.model_validate({"raw_heart_rate_samples": [70, 71]})

    repeated = workout_entry(sample_id=str(uuid4()))
    with pytest.raises(ValidationError):
        HealthKitImportBatchRequest.model_validate(
            {
                "batch_id": str(uuid4()),
                "device_installation_id": str(INSTALLATION_ID),
                "resource_type": "workouts",
                "policy_version": POLICY_VERSION,
                "entries": [repeated.model_dump(mode="json"), repeated.model_dump(mode="json")],
            }
        )
