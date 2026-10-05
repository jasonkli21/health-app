"""Bounded, explicit schemas for manual planning and tracker definitions."""

from __future__ import annotations

import json
from datetime import date, time
from enum import StrEnum
from math import isfinite
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    model_validator,
)

from health_api.domain.schemas import (
    DailyDomain,
    FiniteDailyNumber,
    MeasurementUnit,
    MetricKey,
    ProfileUnit,
    StrictModel,
    validate_iana_timezone,
)


class GoalDomain(StrEnum):
    NUTRITION = "nutrition"
    EXERCISE = "exercise"
    SLEEP = "sleep"
    SYMPTOMS = "symptoms"
    MEASUREMENTS = "measurements"
    GENERAL = "general"


class GoalComparator(StrEnum):
    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    EQUAL = "equal"


class GoalLifecycle(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class RegimenKind(StrEnum):
    HABIT = "habit"
    MEDICATION = "medication"
    SUPPLEMENT = "supplement"
    ACTIVITY = "activity"


class RegimenLifecycle(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class PlanLifecycle(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class ContextLifecycle(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


class TrackerLifecycle(StrEnum):
    ACTIVE = "active"


PlanningLabel = Annotated[StrictStr, StringConstraints(min_length=1, max_length=120)]
BoundedText = Annotated[StrictStr, StringConstraints(max_length=2000)]
FieldId = Annotated[StrictStr, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]


class MetricTarget(StrictModel):
    metric: MetricKey
    comparator: GoalComparator
    value: FiniteDailyNumber
    unit: MeasurementUnit

    @model_validator(mode="after")
    def unit_matches_metric(self) -> MetricTarget:
        supported = {
            MetricKey.ENERGY: {MeasurementUnit.KCAL, MeasurementUnit.KJ},
            MetricKey.DURATION: {MeasurementUnit.MIN, MeasurementUnit.HOUR},
            MetricKey.DISTANCE: {MeasurementUnit.M, MeasurementUnit.KM, MeasurementUnit.MI},
            MetricKey.WEIGHT: {MeasurementUnit.KG, MeasurementUnit.LB},
            MetricKey.TEMPERATURE: {MeasurementUnit.CELSIUS, MeasurementUnit.FAHRENHEIT},
            MetricKey.SYSTOLIC_PRESSURE: {MeasurementUnit.MMHG},
            MetricKey.DIASTOLIC_PRESSURE: {MeasurementUnit.MMHG},
            MetricKey.PULSE: {MeasurementUnit.BPM},
            MetricKey.SYMPTOM_SEVERITY: {MeasurementUnit.SCORE},
            MetricKey.SYMPTOM_EPISODE_COUNT: {MeasurementUnit.EPISODES},
        }
        if self.unit not in supported[self.metric]:
            raise ValueError("goal target unit is not supported for its metric")
        if self.value < 0:
            raise ValueError("goal target quantity must be nonnegative")
        return self


class GoalPayloadV1(StrictModel):
    label: PlanningLabel
    domain: GoalDomain
    target: MetricTarget | None = None
    target_period: Literal["day", "week", "month", "year", "once"] | None = None
    start_date: date | None = None
    target_date: date | None = None

    @model_validator(mode="after")
    def dates_are_ordered(self) -> GoalPayloadV1:
        if self.start_date and self.target_date and self.target_date < self.start_date:
            raise ValueError("target_date must not precede start_date")
        if self.target is None and self.target_period is not None:
            raise ValueError("target_period requires a metric target")
        target_domains = {
            MetricKey.ENERGY: {GoalDomain.NUTRITION},
            MetricKey.DURATION: {GoalDomain.EXERCISE, GoalDomain.SLEEP},
            MetricKey.DISTANCE: {GoalDomain.EXERCISE},
            MetricKey.WEIGHT: {GoalDomain.MEASUREMENTS},
            MetricKey.TEMPERATURE: {GoalDomain.MEASUREMENTS},
            MetricKey.SYSTOLIC_PRESSURE: {GoalDomain.MEASUREMENTS},
            MetricKey.DIASTOLIC_PRESSURE: {GoalDomain.MEASUREMENTS},
            MetricKey.PULSE: {GoalDomain.MEASUREMENTS},
            MetricKey.SYMPTOM_SEVERITY: {GoalDomain.SYMPTOMS},
            MetricKey.SYMPTOM_EPISODE_COUNT: {GoalDomain.SYMPTOMS},
        }
        if self.target is not None and self.domain not in target_domains[self.target.metric]:
            raise ValueError("goal metric does not belong to its domain")
        return self


class EnteredQuantity(StrictModel):
    value: FiniteDailyNumber
    unit: ProfileUnit


class RegimenPayloadV1(StrictModel):
    label: PlanningLabel
    kind: RegimenKind
    domain: GoalDomain = GoalDomain.GENERAL
    quantity: EnteredQuantity | None = None
    instructions: BoundedText | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def dates_are_ordered(self) -> RegimenPayloadV1:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class PlanItemKind(StrEnum):
    GOAL = "goal"
    REGIMEN = "regimen"
    TASK = "task"


class PlanItemInput(StrictModel):
    id: UUID
    kind: PlanItemKind
    label: PlanningLabel
    reference_id: UUID | None = None

    @model_validator(mode="after")
    def reference_matches_kind(self) -> PlanItemInput:
        if (self.kind == PlanItemKind.TASK) == (self.reference_id is not None):
            raise ValueError("tasks have no reference; goal and regimen items require one")
        return self


class PlanPayloadV1(StrictModel):
    label: PlanningLabel
    start_date: date | None = None
    end_date: date | None = None
    items: list[PlanItemInput] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def item_ids_unique_and_dates_ordered(self) -> PlanPayloadV1:
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("plan item IDs must be unique")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class ContextType(StrEnum):
    travel = "travel"
    illness = "illness"
    recovery = "recovery"
    schedule_change = "schedule_change"
    other = "other"


class ContextRelation(StrictModel):
    object_id: UUID
    priority: Annotated[StrictInt, Field(ge=0, le=100)] = 0
    relevance: Annotated[StrictStr, StringConstraints(min_length=1, max_length=32)] = "related"


class ContextPayloadV1(StrictModel):
    label: PlanningLabel
    context_type: ContextType
    notes: BoundedText | None = None
    priority: Annotated[StrictInt, Field(ge=0, le=100)] = 0
    start_at: date | None = None
    end_at: date | None = None
    related: list[ContextRelation] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def dates_are_ordered(self) -> ContextPayloadV1:
        ids = [item.object_id for item in self.related]
        if len(ids) != len(set(ids)):
            raise ValueError("context references must be unique")
        if self.start_at and self.end_at and self.end_at < self.start_at:
            raise ValueError("end_at must not precede start_at")
        return self


class TrackerFieldKind(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"
    DATE = "date"
    QUANTITY = "quantity"


class TrackerFieldV1(StrictModel):
    id: FieldId
    label: PlanningLabel
    kind: TrackerFieldKind
    required: StrictBool = False
    unit: ProfileUnit | None = None
    choices: list[PlanningLabel] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def options_match_kind(self) -> TrackerFieldV1:
        if self.kind == TrackerFieldKind.ENUM:
            if not self.choices or len(set(self.choices)) != len(self.choices):
                raise ValueError("enum fields require unique choices")
        elif self.choices:
            raise ValueError("choices are supported only for enum fields")
        if (self.kind == TrackerFieldKind.QUANTITY) != (self.unit is not None):
            raise ValueError("quantity fields require one supported unit")
        return self


class TrackerDefinitionV1(StrictModel):
    name: PlanningLabel
    domain: DailyDomain
    fields: list[TrackerFieldV1] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def field_ids_are_unique(self) -> TrackerDefinitionV1:
        ids = [item.id for item in self.fields]
        if len(ids) != len(set(ids)):
            raise ValueError("tracker field IDs must be unique")
        if len(json.dumps(self.model_dump(mode="json"), separators=(",", ":")).encode()) > 16_384:
            raise ValueError("tracker definition exceeds 16384 bytes")
        return self


class ScheduleRecurrence(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


class ScheduleDefinitionV1(StrictModel):
    start_date: date
    local_time: time
    timezone: Annotated[StrictStr, StringConstraints(min_length=1, max_length=64)]
    recurrence: ScheduleRecurrence
    interval: Annotated[StrictInt, Field(ge=1, le=365)] = 1
    weekdays: list[Annotated[StrictInt, Field(ge=0, le=6)]] = Field(
        default_factory=list, max_length=7
    )
    end_date: date | None = None

    @model_validator(mode="after")
    def recurrence_is_bounded(self) -> ScheduleDefinitionV1:
        validate_iana_timezone(self.timezone)
        if self.local_time.tzinfo is not None:
            raise ValueError("schedule local_time must not include a timezone offset")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        if self.recurrence == ScheduleRecurrence.WEEKLY and not self.weekdays:
            raise ValueError("weekly schedules require selected weekdays")
        if self.recurrence == ScheduleRecurrence.DAILY and self.weekdays:
            raise ValueError("daily schedules do not use weekdays")
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("weekdays must be unique")
        return self


def validate_tracker_values(
    definition: TrackerDefinitionV1, values: dict[str, object]
) -> dict[str, object]:
    """Validate a flat field-ID map against one immutable tracker definition."""
    fields = {item.id: item for item in definition.fields}
    if set(values) - set(fields):
        raise ValueError("tracker values contain an unknown field")
    validated: dict[str, object] = {}
    for field_id, field in fields.items():
        if field_id not in values:
            if field.required:
                raise ValueError("a required tracker value is missing")
            continue
        value = values[field_id]
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json")
        if field.kind == TrackerFieldKind.TEXT:
            if not isinstance(value, str) or len(value) > 2000:
                raise ValueError("tracker text value is invalid")
        elif field.kind == TrackerFieldKind.BOOLEAN:
            if not isinstance(value, bool):
                raise ValueError("tracker boolean value is invalid")
        elif field.kind == TrackerFieldKind.NUMBER:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or abs(value) > 1e300
            ):
                raise ValueError("tracker number value is invalid")
        elif field.kind == TrackerFieldKind.ENUM:
            if not isinstance(value, str) or value not in field.choices:
                raise ValueError("tracker enum value is invalid")
        elif field.kind == TrackerFieldKind.DATE:
            if not isinstance(value, str):
                raise ValueError("tracker date value is invalid")
            date.fromisoformat(value)
        elif field.kind == TrackerFieldKind.QUANTITY:
            if not isinstance(value, dict) or set(value) != {"value", "unit"}:
                raise ValueError("tracker quantity value is invalid")
            numeric = value["value"]
            if (
                isinstance(numeric, bool)
                or not isinstance(numeric, (int, float))
                or not isfinite(numeric)
                or abs(numeric) > 1e300
            ):
                raise ValueError("tracker quantity value is invalid")
            if value["unit"] != field.unit:
                raise ValueError("tracker quantity unit does not match its definition")
        validated[field_id] = value
    return validated
