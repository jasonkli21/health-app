"""Versioned, strict payload schemas for canonical health objects."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from enum import StrEnum
from math import isfinite
from typing import Annotated, ClassVar, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    FiniteFloat,
    RootModel,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileKind(StrEnum):
    FACT = "fact"
    CONSTRAINT = "constraint"
    PREFERENCE = "preference"


class ProfileCategory(StrEnum):
    BACKGROUND = "background"
    CONSTRAINTS = "constraints"
    PREFERENCES = "preferences"


class ConfirmationStatus(StrEnum):
    UNCONFIRMED = "unconfirmed"
    USER_CONFIRMED = "user_confirmed"


class SourceKind(StrEnum):
    MANUAL = "manual"
    DEVICE = "device"
    DOCUMENT = "document"
    PROVIDER = "provider"
    AI = "ai"
    SYSTEM = "system"


class ProfileUnit(StrEnum):
    KG = "kg"
    G = "g"
    LB = "lb"
    MG = "mg"
    MCG = "mcg"
    ML = "ml"
    L = "l"
    CM = "cm"
    M = "m"
    IN = "in"
    MMHG = "mmHg"
    BPM = "bpm"
    PERCENT = "%"
    DAY = "day"
    WEEK = "week"
    YEAR = "year"
    DOSE = "dose"


def reject_boolean_number(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("boolean values are not numeric Profile values")  # noqa: TRY004
    return value


type FiniteProfileNumber = Annotated[FiniteFloat, BeforeValidator(reject_boolean_number)]


class TextValue(StrictModel):
    type: Literal["text"]
    value: Annotated[StrictStr, StringConstraints(max_length=2000)]


class BooleanValue(StrictModel):
    type: Literal["boolean"]
    value: StrictBool


class NumberValue(StrictModel):
    type: Literal["number"]
    value: FiniteProfileNumber


class QuantityValue(StrictModel):
    type: Literal["quantity"]
    value: FiniteProfileNumber
    unit: ProfileUnit


class TextListValue(StrictModel):
    type: Literal["text_list"]
    value: list[Annotated[StrictStr, StringConstraints(max_length=200)]] = Field(max_length=50)


type ProfileValue = Annotated[
    TextValue | BooleanValue | NumberValue | QuantityValue | TextListValue,
    Field(discriminator="type"),
]

ProfileKey = Annotated[
    StrictStr,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$", min_length=1, max_length=64),
]
ProfileLabel = Annotated[StrictStr, StringConstraints(min_length=1, max_length=120)]
ProfileNotes = Annotated[StrictStr, StringConstraints(max_length=4000)]
DailyNotes = Annotated[StrictStr, StringConstraints(max_length=2000)]
type MetadataScalar = StrictStr | StrictInt | StrictFloat | StrictBool | None


def normalize_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


type UTCInstant = Annotated[AwareDatetime, AfterValidator(normalize_utc)]


class ProfilePayloadV1(StrictModel):
    kind: ProfileKind
    category: ProfileCategory
    key: ProfileKey
    label: ProfileLabel
    # A required null is an explicit unknown value; false and 0 remain known values.
    value: ProfileValue | None

    @model_validator(mode="after")
    def category_matches_kind(self) -> ProfilePayloadV1:
        expected = {
            ProfileKind.FACT: ProfileCategory.BACKGROUND,
            ProfileKind.CONSTRAINT: ProfileCategory.CONSTRAINTS,
            ProfileKind.PREFERENCE: ProfileCategory.PREFERENCES,
        }[self.kind]
        if self.category != expected:
            raise ValueError(f"{self.kind.value} items must use the {expected.value} category")
        return self


type MetadataKey = Annotated[StrictStr, StringConstraints(min_length=1, max_length=64)]


class ProfileMetadata(RootModel[dict[MetadataKey, MetadataScalar]]):
    """Small display-safe extension map; never an unvalidated payload escape hatch."""

    root: dict[MetadataKey, MetadataScalar] = Field(default_factory=dict, max_length=30)

    @model_validator(mode="after")
    def metadata_is_bounded_json(self) -> ProfileMetadata:
        for value in self.root.values():
            if isinstance(value, float) and not isfinite(value):
                raise ValueError("metadata numbers must be finite")
        if len(json.dumps(self.root, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 4096:
            raise ValueError("metadata exceeds 4096 bytes")
        return self


class ProfileValidity(StrictModel):
    valid_from: UTCInstant | None = None
    valid_to: UTCInstant | None = None

    @model_validator(mode="after")
    def validity_is_half_open_and_ordered(self) -> ProfileValidity:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_from >= self.valid_to
        ):
            raise ValueError("valid_from must be earlier than valid_to")
        return self


class ProfileSchemaRegistry:
    """The only lookup path for persisted, versioned type-specific JSON payloads."""

    _schemas: ClassVar[dict[tuple[str, int], type[BaseModel]]] = {
        ("profile_item", 1): ProfilePayloadV1,
    }

    @classmethod
    def get(cls, object_type: str, schema_version: int) -> type[BaseModel]:
        try:
            return cls._schemas[(object_type, schema_version)]
        except KeyError as exc:
            raise ValueError("unsupported object type or schema version") from exc

    @classmethod
    def validate(cls, object_type: str, schema_version: int, payload: object) -> BaseModel:
        return cls.get(object_type, schema_version).model_validate(payload)

    @classmethod
    def register(cls, object_type: str, schema_version: int, schema: type[BaseModel]) -> None:
        key = (object_type, schema_version)
        if key in cls._schemas:
            raise ValueError("schema versions are immutable once registered")
        cls._schemas[key] = schema


class DailyDomain(StrEnum):
    NUTRITION = "nutrition"
    EXERCISE = "exercise"
    SLEEP = "sleep"
    SYMPTOMS = "symptoms"
    MEASUREMENTS = "measurements"


class EventKind(StrEnum):
    MEAL = "meal"
    WORKOUT = "workout"
    SLEEP = "sleep"
    SYMPTOM = "symptom"


class MetricKey(StrEnum):
    ENERGY = "energy"
    DURATION = "duration"
    DISTANCE = "distance"
    WEIGHT = "weight"
    TEMPERATURE = "temperature"
    SYSTOLIC_PRESSURE = "systolic_pressure"
    DIASTOLIC_PRESSURE = "diastolic_pressure"
    PULSE = "pulse"
    SYMPTOM_SEVERITY = "symptom_severity"
    SYMPTOM_EPISODE_COUNT = "symptom_episode_count"


class MeasurementUnit(StrEnum):
    KCAL = "kcal"
    KJ = "kJ"
    MIN = "min"
    HOUR = "h"
    M = "m"
    KM = "km"
    MI = "mi"
    KG = "kg"
    LB = "lb"
    CELSIUS = "C"
    FAHRENHEIT = "F"
    MMHG = "mmHg"
    BPM = "bpm"
    SCORE = "score"
    EPISODES = "episodes"


class InstantTimePoint(StrictModel):
    precision: Literal["instant"]
    occurred_at: UTCInstant
    timezone: Annotated[StrictStr, StringConstraints(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def timezone_is_valid(self) -> InstantTimePoint:
        validate_iana_timezone(self.timezone)
        return self


class DateOnlyTimePoint(StrictModel):
    precision: Literal["date_only"]
    local_date: date
    timezone: Annotated[StrictStr, StringConstraints(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def timezone_is_valid(self) -> DateOnlyTimePoint:
        validate_iana_timezone(self.timezone)
        return self


type DailyTimePoint = Annotated[
    InstantTimePoint | DateOnlyTimePoint,
    Field(discriminator="precision"),
]


class EnergyQuantity(StrictModel):
    value: FiniteProfileNumber
    unit: Literal[MeasurementUnit.KCAL, MeasurementUnit.KJ]

    @model_validator(mode="after")
    def energy_is_nonnegative(self) -> EnergyQuantity:
        if self.value < 0:
            raise ValueError("energy must be nonnegative")
        return self


class DurationQuantity(StrictModel):
    value: FiniteProfileNumber
    unit: Literal[MeasurementUnit.MIN, MeasurementUnit.HOUR]

    @model_validator(mode="after")
    def duration_is_nonnegative(self) -> DurationQuantity:
        if self.value < 0:
            raise ValueError("duration must be nonnegative")
        return self


class DistanceQuantity(StrictModel):
    value: FiniteProfileNumber
    unit: Literal[MeasurementUnit.M, MeasurementUnit.KM, MeasurementUnit.MI]

    @model_validator(mode="after")
    def distance_is_nonnegative(self) -> DistanceQuantity:
        if self.value < 0:
            raise ValueError("distance must be nonnegative")
        return self


class MealEventV1(StrictModel):
    kind: Literal[EventKind.MEAL]
    label: ProfileLabel
    foods: list[Annotated[StrictStr, StringConstraints(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=20
    )
    energy: EnergyQuantity | None = None


class WorkoutEventV1(StrictModel):
    kind: Literal[EventKind.WORKOUT]
    label: ProfileLabel
    duration: DurationQuantity | None = None
    distance: DistanceQuantity | None = None


class SleepEventV1(StrictModel):
    kind: Literal[EventKind.SLEEP]
    label: ProfileLabel = "Sleep"
    quality: Annotated[StrictInt, Field(ge=1, le=5)] | None = None


class SymptomEventV1(StrictModel):
    kind: Literal[EventKind.SYMPTOM]
    label: ProfileLabel


type EventPayloadV1 = Annotated[
    MealEventV1 | WorkoutEventV1 | SleepEventV1 | SymptomEventV1,
    Field(discriminator="kind"),
]


class EventPayloadSchemaV1(RootModel[EventPayloadV1]):
    """Registry wrapper for the JSONB Event payload, excluding relational fields."""


class MeasurementValueV1(StrictModel):
    metric: Literal[
        MetricKey.WEIGHT,
        MetricKey.TEMPERATURE,
        MetricKey.SYSTOLIC_PRESSURE,
        MetricKey.DIASTOLIC_PRESSURE,
        MetricKey.PULSE,
    ]
    value: FiniteProfileNumber
    unit: MeasurementUnit

    @model_validator(mode="after")
    def unit_matches_metric(self) -> MeasurementValueV1:
        supported = {
            MetricKey.WEIGHT: {MeasurementUnit.KG, MeasurementUnit.LB},
            MetricKey.TEMPERATURE: {MeasurementUnit.CELSIUS, MeasurementUnit.FAHRENHEIT},
            MetricKey.SYSTOLIC_PRESSURE: {MeasurementUnit.MMHG},
            MetricKey.DIASTOLIC_PRESSURE: {MeasurementUnit.MMHG},
            MetricKey.PULSE: {MeasurementUnit.BPM},
        }
        if self.unit not in supported[self.metric]:
            raise ValueError("unit is not supported for this measurement")
        if (
            self.metric
            in {
                MetricKey.WEIGHT,
                MetricKey.SYSTOLIC_PRESSURE,
                MetricKey.DIASTOLIC_PRESSURE,
                MetricKey.PULSE,
            }
            and self.value < 0
        ):
            raise ValueError("measurement must be nonnegative")
        return self


class SymptomSeverityV1(StrictModel):
    metric: Literal[MetricKey.SYMPTOM_SEVERITY]
    value: Annotated[StrictInt, Field(ge=0, le=10)]
    unit: Literal[MeasurementUnit.SCORE] = MeasurementUnit.SCORE


type ObservationValueV1 = Annotated[
    MeasurementValueV1 | SymptomSeverityV1,
    Field(discriminator="metric"),
]


class ObservationPayloadV1(StrictModel):
    value: ObservationValueV1


class EventSchemaV1(StrictModel):
    domain: DailyDomain
    time: DailyTimePoint
    ended_at: UTCInstant | None = None
    payload: EventPayloadV1
    notes: DailyNotes | None = None

    @model_validator(mode="after")
    def event_domain_and_interval_match(self) -> EventSchemaV1:
        expected = {
            EventKind.MEAL: DailyDomain.NUTRITION,
            EventKind.WORKOUT: DailyDomain.EXERCISE,
            EventKind.SLEEP: DailyDomain.SLEEP,
            EventKind.SYMPTOM: DailyDomain.SYMPTOMS,
        }[self.payload.kind]
        if self.domain != expected:
            raise ValueError("event kind does not match its domain")
        if self.ended_at is not None:
            if not isinstance(self.time, InstantTimePoint):
                raise ValueError("an interval requires an exact start instant")
            if self.ended_at <= self.time.occurred_at:
                raise ValueError("ended_at must be after occurred_at")
        if self.payload.kind == EventKind.SLEEP and self.ended_at is None:
            raise ValueError("sleep requires a start and end instant")
        if (
            self.payload.kind == EventKind.WORKOUT
            and self.ended_at is not None
            and self.payload.duration is not None
        ):
            raise ValueError("provide workout duration or an end time, not both")
        return self


class ObservationSchemaV1(StrictModel):
    domain: Literal[DailyDomain.MEASUREMENTS, DailyDomain.SYMPTOMS]
    time: DailyTimePoint
    interval_end: UTCInstant | None = None
    payload: ObservationPayloadV1
    notes: DailyNotes | None = None

    @model_validator(mode="after")
    def observation_domain_and_interval_match(self) -> ObservationSchemaV1:
        metric = self.payload.value.metric
        expected = (
            DailyDomain.SYMPTOMS
            if metric == MetricKey.SYMPTOM_SEVERITY
            else DailyDomain.MEASUREMENTS
        )
        if self.domain != expected:
            raise ValueError("observation metric does not match its domain")
        if self.interval_end is not None:
            if not isinstance(self.time, InstantTimePoint):
                raise ValueError("an interval requires an exact observation instant")
            if self.interval_end <= self.time.occurred_at:
                raise ValueError("interval_end must be after occurred_at")
        return self


ProfileSchemaRegistry.register("event", 1, EventPayloadSchemaV1)
ProfileSchemaRegistry.register("observation", 1, ObservationPayloadV1)


def validate_iana_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("must be a valid IANA timezone") from exc
    return name
