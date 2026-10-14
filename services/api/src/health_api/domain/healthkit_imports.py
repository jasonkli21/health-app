"""Strict normalized import contracts for the mobile HealthKit boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    Field,
    StrictInt,
    StrictStr,
    StringConstraints,
    model_validator,
)

from health_api.domain.schemas import (
    EventSchemaV1,
    FiniteDailyNumber,
    ObservationSchemaV1,
    StrictModel,
)


class HealthKitImportMetadata(StrictModel):
    """Allowlisted display/aggregation fields; raw HealthKit metadata is not accepted."""

    sleep_stage: Literal["awake", "asleep", "core", "deep", "rem", "unspecified"] | None = None
    source_bundle_identifier: Annotated[StrictStr, Field(min_length=1, max_length=255)] | None = (
        None
    )
    device_label: Annotated[StrictStr, Field(min_length=1, max_length=80)] | None = None
    aggregation_method_version: Annotated[StrictStr, Field(min_length=1, max_length=64)] | None = (
        None
    )
    sample_count: Annotated[StrictInt, Field(ge=1, le=10_000_000)] | None = None
    minimum: FiniteDailyNumber | None = None
    maximum: FiniteDailyNumber | None = None
    coverage_start: AwareDatetime | None = None
    coverage_end: AwareDatetime | None = None
    source_revision: Annotated[StrictInt, Field(ge=1, le=9_007_199_254_740_991)] | None = None

    @model_validator(mode="after")
    def coverage_is_ordered(self) -> HealthKitImportMetadata:
        if (self.coverage_start is None) != (self.coverage_end is None):
            raise ValueError("coverage_start and coverage_end must be provided together")
        if (
            self.coverage_start is not None
            and self.coverage_end is not None
            and self.coverage_start >= self.coverage_end
        ):
            raise ValueError("coverage_start must be before coverage_end")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")
        return self


class HealthKitImportEntry(StrictModel):
    source_sample_id: Annotated[StrictStr, StringConstraints(min_length=1, max_length=256)]
    record: EventSchemaV1 | ObservationSchemaV1
    metadata: HealthKitImportMetadata = Field(default_factory=HealthKitImportMetadata)


class HealthKitImportTombstone(StrictModel):
    source_sample_id: Annotated[StrictStr, StringConstraints(min_length=1, max_length=256)]
    source_revision: Annotated[StrictInt, Field(ge=1, le=9_007_199_254_740_991)] | None = None


class HealthKitImportBatchRequest(StrictModel):
    batch_id: UUID
    device_installation_id: UUID
    resource_type: Literal[
        "workouts", "sleep", "steps", "weight", "resting_heart_rate", "heart_rate_summary"
    ]
    policy_version: Literal["healthkit-v1"]
    entries: list[HealthKitImportEntry] = Field(default_factory=list, max_length=200)
    tombstones: list[HealthKitImportTombstone] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def batch_is_bounded_and_unambiguous(self) -> HealthKitImportBatchRequest:
        if not 1 <= len(self.entries) + len(self.tombstones) <= 200:
            raise ValueError("batch must contain between one and two hundred changes")
        ids = [item.source_sample_id for item in self.entries]
        ids.extend(item.source_sample_id for item in self.tombstones)
        if len(ids) != len(set(ids)):
            raise ValueError("batch source identities must be unique")
        return self


class HealthKitImportBatchResult(StrictModel):
    batch_id: UUID
    replayed: bool
    created_count: Annotated[StrictInt, Field(ge=0)]
    updated_count: Annotated[StrictInt, Field(ge=0)]
    unchanged_count: Annotated[StrictInt, Field(ge=0)]
    tombstoned_count: Annotated[StrictInt, Field(ge=0)]
    correction_count: Annotated[StrictInt, Field(ge=0)]
    conflict_count: Annotated[StrictInt, Field(ge=0)]


class HealthKitImportTypeStatus(StrictModel):
    resource_type: Literal[
        "workouts", "sleep", "steps", "weight", "resting_heart_rate", "heart_rate_summary"
    ]
    imported_count: Annotated[StrictInt, Field(ge=0)]
    tombstoned_count: Annotated[StrictInt, Field(ge=0)]
    last_success_at: datetime | None
    preferred_installation_id: UUID | None
    preference_revision: Annotated[StrictInt, Field(ge=1)] | None


class HealthKitSourceInstallation(StrictModel):
    device_installation_id: UUID
    source_name: Annotated[StrictStr, Field(min_length=1, max_length=120)]


class HealthKitImportStatusResponse(StrictModel):
    server_ingest_enabled: Literal[True]
    policy_version: Literal["healthkit-v1"]
    types: list[HealthKitImportTypeStatus]
    installations: list[HealthKitSourceInstallation]


class HealthKitSourcePreferenceRequest(StrictModel):
    resource_type: Literal["steps", "heart_rate_summary"]
    device_installation_id: UUID
    expected_revision: Annotated[StrictInt, Field(ge=1)] | None = None


class HealthKitSourcePreferenceResponse(StrictModel):
    resource_type: Literal["steps", "heart_rate_summary"]
    device_installation_id: UUID
    revision: Annotated[StrictInt, Field(ge=1)]
