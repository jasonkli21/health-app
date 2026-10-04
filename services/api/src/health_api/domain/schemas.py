"""Versioned, strict payload schemas for canonical health objects."""

from __future__ import annotations

import json
from datetime import UTC, datetime
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


class ProfileMetadata(StrictModel):
    """Small display-safe extension map; never an unvalidated payload escape hatch."""

    values: dict[
        Annotated[StrictStr, StringConstraints(min_length=1, max_length=64)], MetadataScalar
    ] = Field(default_factory=dict, max_length=30)

    @model_validator(mode="after")
    def metadata_is_bounded_json(self) -> ProfileMetadata:
        for value in self.values.values():
            if isinstance(value, float) and not isfinite(value):
                raise ValueError("metadata numbers must be finite")
        if len(json.dumps(self.values, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 4096:
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


def validate_iana_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("must be a valid IANA timezone") from exc
    return name
