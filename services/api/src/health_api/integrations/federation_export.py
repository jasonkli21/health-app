"""Narrow, purpose-specific Health federation exports."""

from __future__ import annotations

from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

HEALTH_FEDERATION_EXPORT_SCHEMA: Final = "health-federation-export-v1"
HEALTH_FEDERATION_EXPORT_PATH = "/v1/integrations/personal-ai/federation-export"


class HealthFederationExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["health-federation-export-v1"] = HEALTH_FEDERATION_EXPORT_SCHEMA
    application_id: Literal["health"] = "health"
    workspace_id: None = None
    operation: Literal["read", "verify"]
    category: Literal["dietary_restrictions", "ergonomic_constraints"]
    entity_type: Literal["profile_item"] = "profile_item"
    entity_id: UUID
    purpose: Literal[
        "health_dietary_restrictions_to_travel",
        "health_ergonomic_constraints_to_shopping",
    ]
    destination_application_id: Literal["travel", "shopping"]
    fields: tuple[str, ...] = Field(min_length=1, max_length=1)
    max_bytes: Annotated[int, Field(ge=512, le=8192)] = 4096

    @model_validator(mode="after")
    def exact_export_scope(self) -> HealthFederationExportRequest:
        expected = {
            "health_dietary_restrictions_to_travel": (
                "dietary_restrictions",
                "travel",
                "dietary_restrictions",
            ),
            "health_ergonomic_constraints_to_shopping": (
                "ergonomic_constraints",
                "shopping",
                "ergonomic_constraints",
            ),
        }[self.purpose]
        selected_field = "permission_version" if self.operation == "verify" else expected[2]
        if (self.category, self.destination_application_id) != expected[:2] or self.fields != (
            selected_field,
        ):
            raise ValueError("health_federation_export_scope_invalid")
        return self


class HealthFederationSourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["record", "source"]
    reference_id: str = Field(min_length=1, max_length=100)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class HealthFederationPermissionDependency(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    permission_id: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=100)
    source_application_id: Literal["health"] = "health"
    destination_application_id: Literal["travel", "shopping"]


class DietaryRestrictionsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    dietary_restrictions: str | tuple[str, ...] | None


class ErgonomicConstraintsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    ergonomic_constraints: str | tuple[str, ...] | None


HealthFederationPayload = Annotated[
    DietaryRestrictionsPayload | ErgonomicConstraintsPayload,
    Field(discriminator=None),
]


class HealthFederationExportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    category: Literal["dietary_restrictions", "ergonomic_constraints"]
    entity_type: Literal["profile_item"] = "profile_item"
    entity_id: UUID
    source_revision: Annotated[int, Field(ge=1)]
    source_version: str = Field(min_length=1, max_length=100)
    sensitivity: Literal["restricted"] = "restricted"
    payload: HealthFederationPayload | None = None
    source_refs: tuple[HealthFederationSourceReference, ...] = Field(min_length=2, max_length=2)
    permission_dependencies: tuple[HealthFederationPermissionDependency, ...] = Field(
        min_length=1, max_length=1
    )


class HealthFederationExportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["health-federation-export-v1"] = HEALTH_FEDERATION_EXPORT_SCHEMA
    application_id: Literal["health"] = "health"
    workspace_id: None = None
    operation: Literal["read", "verify"]
    complete: StrictBool = True
    authoritative_empty: StrictBool = False
    continuation: None = None
    item: HealthFederationExportRecord
