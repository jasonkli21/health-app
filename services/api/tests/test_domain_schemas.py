from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from health_api.domain.schemas import (
    ProfileCategory,
    ProfileKind,
    ProfileMetadata,
    ProfilePayloadV1,
    ProfileSchemaRegistry,
    ProfileValidity,
)


def fact(value: object = None, **overrides: object) -> dict[str, object]:
    return {
        "kind": "fact",
        "category": "background",
        "key": "diet_preference",
        "label": "Diet preference",
        "value": value,
        **overrides,
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ({"type": "boolean", "value": False}, False),
        ({"type": "number", "value": 0}, 0.0),
        ({"type": "text", "value": "Vegetarian"}, "Vegetarian"),
    ],
)
def test_profile_v1_preserves_unknown_false_zero_and_typed_values(
    value: object, expected: object
) -> None:
    payload = ProfilePayloadV1.model_validate(fact(value))
    assert payload.value is None if expected is None else payload.value.value == expected


def test_registry_is_explicit_and_rejects_future_versions() -> None:
    assert isinstance(ProfileSchemaRegistry.validate("profile_item", 1, fact()), ProfilePayloadV1)
    with pytest.raises(ValueError, match="unsupported"):
        ProfileSchemaRegistry.validate("profile_item", 2, fact())


def test_profile_v1_rejects_unknown_fields_and_category_kind_mismatch() -> None:
    with pytest.raises(ValidationError):
        ProfilePayloadV1.model_validate(fact(extra_health_field="not allowed"))
    with pytest.raises(ValidationError, match="must use"):
        ProfilePayloadV1.model_validate(fact(category="constraints"))


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_profile_numeric_values_must_be_finite(number: float) -> None:
    with pytest.raises(ValidationError):
        ProfilePayloadV1.model_validate(fact({"type": "quantity", "value": number, "unit": "kg"}))


def test_quantity_rejects_unsupported_units_and_boolean_numbers() -> None:
    with pytest.raises(ValidationError):
        ProfilePayloadV1.model_validate(fact({"type": "quantity", "value": 2, "unit": "stone"}))
    with pytest.raises(ValidationError):
        ProfilePayloadV1.model_validate(fact({"type": "number", "value": True}))


def test_profile_metadata_is_bounded_and_rejects_non_finite_numbers() -> None:
    assert ProfileMetadata.model_validate({"display_unit": "kg"}).root == {"display_unit": "kg"}
    with pytest.raises(ValidationError):
        ProfileMetadata.model_validate({"display_unit": float("inf")})
    with pytest.raises(ValidationError):
        ProfileMetadata.model_validate({"display_unit": "x" * 5000})


def test_validity_requires_aware_ordered_instants_and_normalizes_to_utc() -> None:
    value = ProfileValidity(
        valid_from=datetime.fromisoformat("2026-10-03T12:00:00+02:00"),
        valid_to=datetime.fromisoformat("2026-10-04T12:00:00+02:00"),
    )
    assert value.valid_from == datetime(2026, 10, 3, 10, tzinfo=UTC)

    with pytest.raises(ValidationError):
        ProfileValidity(valid_from=datetime.fromisoformat("2026-10-03T00:00:00"), valid_to=None)
    with pytest.raises(ValidationError, match="earlier"):
        ProfileValidity(
            valid_from=datetime(2026, 10, 3, tzinfo=UTC),
            valid_to=datetime(2026, 10, 3, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("kind", "category"),
    [
        (ProfileKind.CONSTRAINT, ProfileCategory.CONSTRAINTS),
        (ProfileKind.PREFERENCE, ProfileCategory.PREFERENCES),
    ],
)
def test_supported_profile_categories_are_explicit(
    kind: ProfileKind, category: ProfileCategory
) -> None:
    payload = ProfilePayloadV1.model_validate(
        {**fact(None), "kind": kind.value, "category": category.value}
    )
    assert payload.kind == kind
