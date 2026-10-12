"""Versioned read-only Health context wire contract for Personal AI.

This contract is intentionally separate from the Health-local ``AIContextPack``.
It carries no owner authority, writes, proposal commands, or untyped global profile.
"""

from __future__ import annotations

from datetime import timedelta
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    StrictInt,
    model_validator,
)

from health_api.domain.schemas import (
    DailyTimePoint,
    EventPayloadSchemaV1,
    MetricKey,
    ObservationPayloadV1,
    ProfileCategory,
    ProfilePayloadV1,
)

HEALTH_CONTEXT_SCHEMA: Literal["health-context-read-v1"] = "health-context-read-v1"
HEALTH_CONTEXT_PATH = "/v1/integrations/personal-ai/context"
HEALTH_CONTEXT_MAX_WINDOW = timedelta(days=90)
HEALTH_CONTEXT_MAX_RESULTS = 32
HEALTH_CONTEXT_MAX_BYTES = 32_768

HealthContextCategory = Literal[
    "profile_background",
    "profile_constraints",
    "profile_preferences",
    "measurements",
    "nutrition",
    "exercise",
    "sleep",
    "symptoms",
]
HealthResourceType = Literal["profile_item", "event", "observation"]
HealthSourceKind = Literal["manual", "device", "document", "provider", "ai", "system"]
HealthConfirmation = Literal["unconfirmed", "user_confirmed"]
HealthAuthority = Literal["authoritative"]
HealthSensitivity = Literal["personal", "sensitive", "restricted"]

PROFILE_CATEGORIES = frozenset(
    {"profile_background", "profile_constraints", "profile_preferences"}
)
DAILY_CATEGORIES = frozenset({"measurements", "nutrition", "exercise", "sleep", "symptoms"})
PROFILE_FIELDS = frozenset(
    {"record", "notes", "source_kind", "confirmation_status", "validity"}
)
DAILY_FIELDS = frozenset(
    {
        "record",
        "domain",
        "notes",
        "time",
        "interval_end",
        "units",
        "source_kind",
        "confirmation_status",
        "quality",
        "uncertainty",
    }
)


class HealthContextEntityReference(BaseModel):
    """A Health-owned object reference; it is a selector, never an owner credential."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    object_type: HealthResourceType
    object_id: UUID


class HealthContextReadRequest(BaseModel):
    """An exact bounded read or permission revalidation request."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["health-context-read-v1"] = HEALTH_CONTEXT_SCHEMA
    application_id: Literal["health"] = "health"
    workspace_id: None = None
    purpose: Literal["personal_ai_context"] = "personal_ai_context"
    operation: Literal["catalog", "profile", "history", "time_series", "verify"]
    category: HealthContextCategory | None = None
    entity_refs: tuple[HealthContextEntityReference, ...] = Field(default=(), max_length=16)
    fields: tuple[str, ...] = Field(default=(), max_length=12)
    window_start: AwareDatetime | None = None
    window_end: AwareDatetime | None = None
    max_results: Annotated[StrictInt, Field(ge=1, le=HEALTH_CONTEXT_MAX_RESULTS)] = 8
    max_bytes: Annotated[StrictInt, Field(ge=512, le=HEALTH_CONTEXT_MAX_BYTES)] = 16_384

    @model_validator(mode="after")
    def scope_is_exact_and_bounded(self) -> HealthContextReadRequest:
        if len(set(self.entity_refs)) != len(self.entity_refs):
            raise ValueError("health_context_entity_refs_not_unique")
        if len(set(self.fields)) != len(self.fields):
            raise ValueError("health_context_fields_not_unique")
        window_start = self.window_start
        window_end = self.window_end
        if (window_start is None) != (window_end is None):
            raise ValueError("health_context_window_incomplete")
        if window_start is not None and window_end is not None:
            if window_end <= window_start:
                raise ValueError("health_context_window_invalid")
            if window_end - window_start > HEALTH_CONTEXT_MAX_WINDOW:
                raise ValueError("health_context_window_too_large")

        if self.operation == "catalog":
            if self.category is not None or self.entity_refs or self.fields or self.window_start:
                raise ValueError("health_context_catalog_scope_invalid")
            return self
        if self.category is None:
            raise ValueError("health_context_category_required")
        if self.operation == "verify":
            if len(self.entity_refs) != 1 or self.fields != ("permission_version",):
                raise ValueError("health_context_verify_scope_invalid")
            if self.window_start is not None:
                raise ValueError("health_context_verify_window_invalid")
            if self.category in PROFILE_CATEGORIES and self.entity_refs[0].object_type != "profile_item":
                raise ValueError("health_context_verify_entity_type_invalid")
            if self.category == "measurements" and self.entity_refs[0].object_type != "observation":
                raise ValueError("health_context_verify_entity_type_invalid")
            if self.category in DAILY_CATEGORIES - {"measurements"} and self.entity_refs[0].object_type not in {"event", "observation"}:
                raise ValueError("health_context_verify_entity_type_invalid")
            return self

        if self.category in PROFILE_CATEGORIES:
            if self.operation != "profile" or self.window_start is not None:
                raise ValueError("health_context_profile_scope_invalid")
            if any(item.object_type != "profile_item" for item in self.entity_refs):
                raise ValueError("health_context_profile_entity_type_invalid")
            allowed_fields = PROFILE_FIELDS
        else:
            if self.operation not in {"history", "time_series"}:
                raise ValueError("health_context_daily_operation_invalid")
            if self.operation == "time_series" and self.category != "measurements":
                raise ValueError("health_context_time_series_category_invalid")
            if self.operation == "history" and self.category == "measurements":
                raise ValueError("health_context_measurement_history_requires_time_series")
            if self.window_start is None or self.window_end is None:
                raise ValueError("health_context_history_window_required")
            if any(item.object_type == "profile_item" for item in self.entity_refs):
                raise ValueError("health_context_daily_entity_type_invalid")
            allowed_fields = DAILY_FIELDS
        if not self.fields or not set(self.fields) <= allowed_fields:
            raise ValueError("health_context_fields_invalid")
        return self


class HealthContextFieldSensitivity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    field: str = Field(min_length=1, max_length=80)
    sensitivity: HealthSensitivity


class HealthContextSourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    kind: Literal["record", "source"]
    reference_id: str = Field(min_length=1, max_length=100)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class HealthContextPermissionDependency(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    permission_id: str = Field(
        pattern=(
            r"^health_context_read:(profile_background|profile_constraints|profile_preferences|"
            r"measurements|nutrition|exercise|sleep|symptoms):"
            r"(profile_item|event|observation):[0-9a-f-]{36}$"
        ),
        max_length=160,
    )
    version: str = Field(min_length=1, max_length=100)
    purpose: Literal["personal_ai_context"] = "personal_ai_context"


class HealthContextPayload(BaseModel):
    """A domain-typed selected projection, with explicit per-field sensitivity."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    category: HealthContextCategory
    object_type: HealthResourceType
    domain: str | None = Field(default=None, max_length=32)
    record: JsonValue | None = None
    notes: str | None = Field(default=None, max_length=2_000)
    time: DailyTimePoint | None = None
    interval_end: AwareDatetime | None = None
    units: dict[str, str] | None = Field(default=None, max_length=8)
    source_kind: HealthSourceKind | None = None
    confirmation_status: HealthConfirmation | None = None
    quality: dict[str, JsonValue] | None = Field(default=None, max_length=8)
    uncertainty: str | None = Field(default=None, max_length=160)
    validity: dict[str, AwareDatetime | None] | None = None

    @model_validator(mode="after")
    def typed_payload_matches_category(self) -> HealthContextPayload:
        if self.category in PROFILE_CATEGORIES:
            if self.object_type != "profile_item":
                raise ValueError("health_context_profile_type_mismatch")
            if self.record is not None:
                try:
                    validated = ProfilePayloadV1.model_validate(self.record)
                except ValueError as error:
                    raise ValueError("health_context_profile_payload_invalid") from error
                expected_profile_category = {
                    "profile_background": ProfileCategory.BACKGROUND,
                    "profile_constraints": ProfileCategory.CONSTRAINTS,
                    "profile_preferences": ProfileCategory.PREFERENCES,
                }[self.category]
                if validated.category != expected_profile_category:
                    raise ValueError("health_context_profile_category_mismatch")
        else:
            if self.object_type not in {"event", "observation"}:
                raise ValueError("health_context_daily_type_mismatch")
            if self.category == "measurements" and self.object_type != "observation":
                raise ValueError("health_context_measurement_type_mismatch")
            if self.domain != self.category:
                raise ValueError("health_context_daily_domain_mismatch")
            if self.record is not None:
                try:
                    if self.object_type == "event":
                        validated_event = EventPayloadSchemaV1.model_validate(self.record)
                        expected_daily_category = {
                            "meal": "nutrition",
                            "workout": "exercise",
                            "sleep": "sleep",
                            "symptom": "symptoms",
                        }[validated_event.root.kind.value]
                    else:
                        validated_observation = ObservationPayloadV1.model_validate(self.record)
                        metric = validated_observation.value.metric
                        if isinstance(metric, str) and metric == "custom":
                            raise ValueError("custom_tracker_context_not_supported")
                        metric_key = metric.value if isinstance(metric, Enum) else metric
                        expected_daily_category = (
                            "symptoms"
                            if metric_key == MetricKey.SYMPTOM_SEVERITY
                            else "exercise"
                            if metric_key == MetricKey.STEPS
                            else "measurements"
                        )
                except ValueError as error:
                    raise ValueError("health_context_daily_payload_invalid") from error
                if expected_daily_category != self.category:
                    raise ValueError("health_context_daily_category_mismatch")
        if self.object_type == "profile_item" and (self.time is not None or self.interval_end is not None):
            raise ValueError("health_context_profile_time_invalid")
        return self


class HealthContextRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    object_id: UUID
    object_type: HealthResourceType
    object_revision: Annotated[StrictInt, Field(ge=1)]
    schema_version: Annotated[StrictInt, Field(ge=1)]
    source_id: UUID
    source_version: str = Field(min_length=1, max_length=100)
    source_kind: HealthSourceKind
    confirmation_status: HealthConfirmation
    authority: HealthAuthority = "authoritative"
    observed_at: AwareDatetime
    effective_at: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    active_state: Literal["active"] = "active"
    sensitivity: HealthSensitivity = "restricted"
    field_sensitivity: tuple[HealthContextFieldSensitivity, ...] = Field(
        min_length=1, max_length=12
    )
    source_refs: tuple[HealthContextSourceReference, ...] = Field(min_length=2, max_length=2)
    permission_dependencies: tuple[HealthContextPermissionDependency, ...] = Field(min_length=1, max_length=1)
    payload: HealthContextPayload

    @model_validator(mode="after")
    def projection_metadata_is_complete(self) -> HealthContextRecord:
        if self.expires_at is not None and self.expires_at <= self.observed_at:
            raise ValueError("health_context_expiry_invalid")
        if self.payload.object_type != self.object_type:
            raise ValueError("health_context_payload_object_type_mismatch")
        if len({label.field for label in self.field_sensitivity}) != len(self.field_sensitivity):
            raise ValueError("health_context_field_sensitivity_duplicate")
        payload_fields = set(self.payload.model_dump(exclude_none=True)) - {
            "category",
            "object_type",
        }
        if payload_fields - {item.field for item in self.field_sensitivity}:
            raise ValueError("health_context_field_sensitivity_missing")
        if self.sensitivity != "restricted":
            raise ValueError("health_context_sensitivity_understated")
        return self


class HealthContextCategoryOption(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    category: HealthContextCategory
    display_name: str = Field(min_length=1, max_length=64)
    sensitivity: Literal["restricted"] = "restricted"


class HealthContextPermissionVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    object_id: UUID
    version: str = Field(min_length=1, max_length=100)


class HealthContextReadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["health-context-read-v1"] = HEALTH_CONTEXT_SCHEMA
    application_id: Literal["health"] = "health"
    workspace_id: None = None
    operation: Literal["catalog", "profile", "history", "time_series", "verify"]
    items: tuple[HealthContextRecord, ...] = Field(default=(), max_length=HEALTH_CONTEXT_MAX_RESULTS)
    categories: tuple[HealthContextCategoryOption, ...] = Field(default=(), max_length=8)
    permission_versions: tuple[HealthContextPermissionVersion, ...] = Field(default=(), max_length=16)
    truncated: StrictBool = False

    @model_validator(mode="after")
    def response_shape_matches_operation(self) -> HealthContextReadResponse:
        if self.operation == "catalog":
            if self.items or self.permission_versions or len({item.category for item in self.categories}) != len(self.categories):
                raise ValueError("health_context_catalog_response_invalid")
        elif self.operation == "verify":
            if self.items or self.categories or len({item.object_id for item in self.permission_versions}) != len(self.permission_versions):
                raise ValueError("health_context_verify_response_invalid")
        elif self.categories or self.permission_versions:
            raise ValueError("health_context_categories_unexpected")
        return self
