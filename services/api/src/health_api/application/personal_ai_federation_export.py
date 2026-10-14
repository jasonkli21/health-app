"""Resolve current source consent and return one narrow Health federation field."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from health_api.application.ai_context_admission import _eligibility_conditions
from health_api.domain.schemas import ProfilePayloadV1, ProfileSchemaRegistry
from health_api.integrations.federation_export import (
    DietaryRestrictionsPayload,
    ErgonomicConstraintsPayload,
    HealthFederationExportRecord,
    HealthFederationExportRequest,
    HealthFederationExportResponse,
    HealthFederationPermissionDependency,
    HealthFederationSourceReference,
)
from health_api.persistence.models import HealthObject, ProfileItem, Source


class HealthFederationExportDenied(ValueError):
    """Stable source-domain rejection for absent, stale, or unconsented exports."""


_PURPOSE_FIELDS = {
    "health_dietary_restrictions_to_travel": "dietary_restrictions",
    "health_ergonomic_constraints_to_shopping": "ergonomic_constraints",
}


def _version(obj: HealthObject) -> str:
    return (
        f"health-object-v1:r{obj.revision}:ai{int(obj.ai_use_allowed)}:"
        f"cross{int(obj.cross_domain_use_allowed)}"
    )


def read_health_federation_export(
    session: Session,
    owner_id: UUID,
    request: HealthFederationExportRequest,
    *,
    now: datetime | None = None,
) -> HealthFederationExportResponse:
    """Read exactly one consented constraints key; never return its full profile record."""
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    field = _PURPOSE_FIELDS[request.purpose]
    if request.category != field:
        raise HealthFederationExportDenied("health_federation_export_scope_invalid")

    conditions = _eligibility_conditions(
        owner_id,
        object_type="profile_item",
        payload=ProfileItem.payload,
        as_of=current_time,
        start_date=current_time.date(),
        start_at=current_time,
        end_date=current_time.date(),
        require_cross_domain=True,
    )
    conditions.extend(
        (
            HealthObject.id == request.entity_id,
            ProfileItem.category == "constraints",
            ProfileItem.key == field,
        )
    )
    row = session.execute(
        select(HealthObject, ProfileItem, Source)
        .join(
            ProfileItem,
            and_(
                ProfileItem.owner_id == HealthObject.owner_id,
                ProfileItem.object_id == HealthObject.id,
            ),
        )
        .join(
            Source,
            and_(Source.owner_id == HealthObject.owner_id, Source.id == HealthObject.source_id),
        )
        .where(*conditions)
        .limit(1)
    ).one_or_none()
    if row is None:
        raise HealthFederationExportDenied("health_federation_export_denied")

    obj, profile, source = row
    version = _version(obj)
    permission_id = f"health_federation:{request.purpose}:{obj.id}"
    dependency = HealthFederationPermissionDependency(
        permission_id=permission_id,
        version=version,
        purpose=request.purpose,
        destination_application_id=request.destination_application_id,
    )
    fingerprint = hashlib.sha256(
        json.dumps(
            {"entity_id": str(obj.id), "revision": obj.revision, "purpose": request.purpose},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    references = (
        HealthFederationSourceReference(
            kind="record", reference_id=str(obj.id), fingerprint=fingerprint
        ),
        HealthFederationSourceReference(
            kind="source", reference_id=str(source.id), fingerprint=fingerprint
        ),
    )
    payload = None
    authoritative_empty = False
    if request.operation == "read":
        try:
            value = ProfileSchemaRegistry.get(
                "profile_item", profile.payload.get("schema_version", 1)
            )
            validated = value.model_validate(profile.payload)
        except Exception as error:
            raise HealthFederationExportDenied("health_federation_source_invalid") from error
        if not isinstance(validated, ProfilePayloadV1) or validated.key != field:
            raise HealthFederationExportDenied("health_federation_source_invalid")
        raw_value: Any = validated.value
        normalized: str | tuple[str, ...] | None
        if raw_value is None:
            normalized = None
        elif raw_value.type == "text":
            normalized = raw_value.value
        elif raw_value.type == "text_list":
            normalized = tuple(raw_value.value)
        else:
            raise HealthFederationExportDenied("health_federation_value_type_unsupported")
        authoritative_empty = normalized is None or normalized == "" or normalized == ()
        payload = (
            DietaryRestrictionsPayload(dietary_restrictions=normalized)
            if field == "dietary_restrictions"
            else ErgonomicConstraintsPayload(ergonomic_constraints=normalized)
        )

    item = HealthFederationExportRecord(
        category=request.category,
        entity_id=obj.id,
        source_revision=obj.revision,
        source_version=f"health-object-v1:r{obj.revision}:schema-{obj.schema_version}",
        payload=payload,
        source_refs=references,
        permission_dependencies=(dependency,),
    )
    return HealthFederationExportResponse(
        operation=request.operation,
        authoritative_empty=authoritative_empty,
        item=item,
    )
