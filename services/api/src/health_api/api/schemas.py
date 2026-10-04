"""Typed HTTP transport schemas for the Profile v1 API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from health_api.domain.schemas import (
    ConfirmationStatus,
    ProfileMetadata,
    ProfileNotes,
    ProfilePayloadV1,
    ProfileValidity,
    StrictModel,
)
from pydantic import AwareDatetime, ConfigDict, Field, StrictBool, StrictInt, model_validator


def _non_null_openapi_schema(schema: dict[str, Any]) -> None:
    """The field may be omitted, but explicit JSON null is rejected by the model validator."""
    alternatives = schema.get("anyOf")
    if not isinstance(alternatives, list):
        return
    non_null = [alternative for alternative in alternatives if alternative.get("type") != "null"]
    if len(non_null) == 1:
        schema.pop("anyOf")
        schema.update(non_null[0])
    else:
        schema["anyOf"] = non_null


class ProfileCreateRequest(ProfileValidity):
    id: UUID
    profile: ProfilePayloadV1
    ai_use_allowed: StrictBool = False
    cross_domain_use_allowed: StrictBool = False
    notes: ProfileNotes | None = None
    metadata: ProfileMetadata = Field(default_factory=ProfileMetadata)


class ProfilePatchRequest(StrictModel):
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    profile: ProfilePayloadV1 | None = Field(
        default=None,
        description="Omit to keep the current payload; explicit null is invalid.",
        json_schema_extra=_non_null_openapi_schema,
    )
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None
    ai_use_allowed: StrictBool | None = Field(
        default=None, json_schema_extra=_non_null_openapi_schema
    )
    cross_domain_use_allowed: StrictBool | None = Field(
        default=None, json_schema_extra=_non_null_openapi_schema
    )
    notes: ProfileNotes | None = None
    metadata: ProfileMetadata | None = None

    @model_validator(mode="after")
    def reject_null_for_nonnullable_fields(self) -> ProfilePatchRequest:
        for name in (
            "profile",
            "ai_use_allowed",
            "cross_domain_use_allowed",
        ):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_from >= self.valid_to
        ):
            raise ValueError("valid_from must be earlier than valid_to")
        return self

    def changes(self) -> dict[str, object]:
        result: dict[str, object] = {}
        for name in self.model_fields_set - {"expected_revision"}:
            value = getattr(self, name)
            if name == "profile" and value is not None:
                result[name] = value.model_dump(mode="json")
            elif name == "metadata":
                result[name] = value.root if isinstance(value, ProfileMetadata) else {}
            else:
                result[name] = value
        return result


class ProfilePermissions(StrictModel):
    ai_use_allowed: StrictBool
    cross_domain_use_allowed: StrictBool


class ProfileSource(StrictModel):
    id: UUID
    kind: Literal["manual", "device", "document", "provider", "ai", "system"]
    name: Annotated[str, Field(min_length=1, max_length=120)]


class ProfileItemResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    object_type: Literal["profile_item"]
    domain: Literal["profile"]
    status: Literal["active", "archived"]
    title: Annotated[str, Field(min_length=1, max_length=120)]
    valid_from: datetime | None
    valid_to: datetime | None
    recorded_at: datetime
    created_at: datetime
    updated_at: datetime
    source: ProfileSource
    confirmation_status: ConfirmationStatus
    schema_version: Literal[1]
    revision: Annotated[int, Field(ge=1)]
    notes: ProfileNotes | None
    metadata: ProfileMetadata
    permissions: ProfilePermissions
    profile: ProfilePayloadV1


class ProfileListResponse(StrictModel):
    items: list[ProfileItemResponse]
    as_of: AwareDatetime
    next_cursor: str | None


class ProfileHistoryEntry(StrictModel):
    revision: Annotated[int, Field(ge=1)]
    recorded_at: datetime
    actor_kind: Literal["user"]
    reason: Literal["create", "update", "archive"]
    snapshot: ProfileItemResponse


class ProfileHistoryResponse(StrictModel):
    items: list[ProfileHistoryEntry]
    next_after_revision: int | None


class FieldError(StrictModel):
    field: str
    message: str


class ErrorResponse(StrictModel):
    code: str
    message: str
    field_errors: list[FieldError] | None = None
    request_id: str
