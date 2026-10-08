"""Tracker schema history and custom-entry validation.

Validation and schema-history reads join the caller's owner-scoped unit of
work. The observation validator locks the tracker row until that transaction
finishes; callers lock the owner first, then any referenced objects in sorted
ID order when applying a multi-command proposal.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from health_api.application.errors import DailyNotFound, DailyValidationError, PlanningNotFound
from health_api.domain.planning import TrackerDefinitionV1, validate_tracker_values
from health_api.domain.schemas import CustomTrackerValueV1, ObservationSchemaV1
from health_api.persistence.models import HealthObject, PlanningResource, TrackerSchemaVersion
from pydantic import ValidationError
from sqlalchemy import and_, select
from sqlalchemy.orm import Session


def append_tracker_schema_version(
    session: Session, owner_id: UUID, tracker_id: UUID, version: int, definition: dict[str, Any]
) -> None:
    """Append one immutable schema version inside the caller's transaction."""
    session.add(
        TrackerSchemaVersion(
            owner_id=owner_id, tracker_id=tracker_id, version=version, definition=definition
        )
    )


def list_tracker_schema_versions(
    session: Session, owner_id: UUID, tracker_id: UUID, after_version: int, limit: int
) -> list[TrackerSchemaVersion]:
    """Return owner-scoped immutable tracker schemas after validating the target."""
    exists = session.scalar(
        select(HealthObject.id)
        .join(
            PlanningResource,
            and_(
                PlanningResource.owner_id == HealthObject.owner_id,
                PlanningResource.object_id == HealthObject.id,
            ),
        )
        .where(
            HealthObject.owner_id == owner_id,
            HealthObject.id == tracker_id,
            HealthObject.object_type == "tracker_definition",
            PlanningResource.resource_kind == "tracker_definition",
        )
    )
    if exists is None:
        raise PlanningNotFound
    return list(
        session.scalars(
            select(TrackerSchemaVersion)
            .where(
                TrackerSchemaVersion.owner_id == owner_id,
                TrackerSchemaVersion.tracker_id == tracker_id,
                TrackerSchemaVersion.version > after_version,
            )
            .order_by(TrackerSchemaVersion.version.asc())
            .limit(limit)
        )
    )


def validate_tracker_observation(
    session: Session, owner_id: UUID, schema: ObservationSchemaV1, *, allow_archived: bool = False
) -> None:
    """Validate custom values against their immutable, owner-scoped schema."""
    value = schema.payload.value
    if not isinstance(value, CustomTrackerValueV1):
        return
    row = session.execute(
        select(HealthObject, PlanningResource)
        .join(
            PlanningResource,
            and_(
                PlanningResource.owner_id == HealthObject.owner_id,
                PlanningResource.object_id == HealthObject.id,
            ),
        )
        .where(
            HealthObject.owner_id == owner_id,
            HealthObject.id == value.tracker_id,
            HealthObject.object_type == "tracker_definition",
        )
        .with_for_update()
    ).one_or_none()
    if row is None:
        raise DailyNotFound
    tracker, resource = row
    if not allow_archived and (tracker.status != "active" or resource.lifecycle != "active"):
        raise DailyValidationError("archived trackers do not accept new entries")
    schema_version = session.get(
        TrackerSchemaVersion, (owner_id, value.tracker_id, value.schema_version)
    )
    if schema_version is None:
        raise DailyNotFound
    try:
        definition = TrackerDefinitionV1.model_validate(schema_version.definition)
        values = validate_tracker_values(definition, value.values)
    except (ValidationError, ValueError) as exc:
        raise DailyValidationError(
            "tracker values do not match the selected schema version"
        ) from exc
    if definition.domain != schema.domain:
        raise DailyValidationError("tracker domain does not match the Observation")
    value.values = values
