"""Transactional, owner-scoped ingestion of bounded normalized HealthKit batches."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import UUID, uuid5

from pydantic import ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from health_api.application.analytics_service import invalidate_analytics
from health_api.application.daily_service import (
    CreateDailyEntry,
    CreateDailyEvent,
    CreateDailyObservation,
    archive_daily_item,
    create_daily_entry,
    get_daily_item,
    update_daily_item,
)
from health_api.application.envelope_service import (
    healthkit_source,
    next_daily_sequence,
    unit_of_work,
)
from health_api.application.errors import DailyConflict, DailyNotFound, DailyValidationError
from health_api.domain.daily import local_day_bounds
from health_api.domain.healthkit_imports import (
    HealthKitImportBatchRequest,
    HealthKitImportBatchResult,
    HealthKitImportEntry,
    HealthKitImportMetadata,
    HealthKitImportStatusResponse,
    HealthKitImportTypeStatus,
    HealthKitSourceInstallation,
    HealthKitSourcePreferenceRequest,
    HealthKitSourcePreferenceResponse,
)
from health_api.domain.schemas import (
    DailyDomain,
    DateOnlyTimePoint,
    EventKind,
    EventSchemaV1,
    InstantTimePoint,
    MeasurementValueV1,
    MetricKey,
    ObservationSchemaV1,
    ProfileMetadata,
    StepCountValueV1,
)
from health_api.persistence.models import (
    DailySnapshotMarker,
    HealthKitImportBatch,
    HealthKitImportIdentity,
    HealthKitSourcePreference,
    HealthObject,
    Source,
    User,
)

AGGREGATE_TYPES = {"steps", "heart_rate_summary"}
RESOURCE_TYPES = (
    "workouts",
    "sleep",
    "steps",
    "weight",
    "resting_heart_rate",
    "heart_rate_summary",
)


class HealthKitImportConflict(Exception):
    """A batch or source identity conflicts with a previously accepted import."""


class HealthKitImportValidationError(Exception):
    """A normalized HealthKit entry does not match its declared type or policy."""


def _metadata_dict(metadata: HealthKitImportMetadata) -> dict[str, Any]:
    return metadata.model_dump(mode="json", exclude_none=True)


def _canonical_sample_id(source_sample_id: str) -> str:
    try:
        return str(UUID(source_sample_id))
    except ValueError:
        return source_sample_id


def _canonical_entry(entry: HealthKitImportEntry) -> dict[str, Any]:
    return {
        "source_sample_id": _canonical_sample_id(entry.source_sample_id),
        "record": entry.record.model_dump(mode="json", exclude_none=True),
        "metadata": _metadata_dict(entry.metadata),
    }


def _batch_content_hash(batch: HealthKitImportBatchRequest) -> str:
    content = {
        "device_installation_id": str(batch.device_installation_id),
        "resource_type": batch.resource_type,
        "policy_version": batch.policy_version,
        "entries": sorted(
            (_canonical_entry(item) for item in batch.entries), key=lambda x: x["source_sample_id"]
        ),
        "tombstones": sorted(
            _canonical_sample_id(item.source_sample_id) for item in batch.tombstones
        ),
    }
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _metadata_for_object(
    resource_type: str,
    source_sample_id: str,
    policy_version: str,
    metadata: HealthKitImportMetadata,
) -> dict[str, Any]:
    normalized = _metadata_dict(metadata)
    for key in ("coverage_start", "coverage_end"):
        value = getattr(metadata, key)
        if value is not None:
            normalized[key] = value.astimezone(UTC).isoformat()
    fields = {
        "healthkit_resource_type": resource_type,
        "healthkit_source_sample_id": source_sample_id,
        "healthkit_policy_version": policy_version,
        **{f"healthkit_{key}": value for key, value in normalized.items()},
    }
    try:
        return dict(ProfileMetadata.model_validate(fields).root)
    except (TypeError, ValueError) as exc:
        raise HealthKitImportValidationError("import metadata is invalid") from exc


def _is_aggregate_record(entry: HealthKitImportEntry, resource_type: str) -> bool:
    record = entry.record
    return resource_type in AGGREGATE_TYPES and isinstance(record, ObservationSchemaV1)


def _validate_entry(
    entry: HealthKitImportEntry,
    resource_type: str,
    installation_id: UUID,
    policy_version: str,
) -> tuple[date | None, str | None]:
    record = entry.record
    metadata = entry.metadata
    if record.notes is not None:
        raise HealthKitImportValidationError("imported records cannot contain notes")
    metadata_fields = set(metadata.model_fields_set)
    common_fields = {"source_bundle_identifier", "device_label"}
    specific_fields: set[str]

    def check_metadata_fields() -> None:
        if metadata_fields - common_fields - specific_fields:
            raise HealthKitImportValidationError("metadata fields are not allowed for this type")

    if resource_type == "workouts":
        specific_fields = set()
        if not isinstance(record, EventSchemaV1) or record.payload.kind != EventKind.WORKOUT:
            raise HealthKitImportValidationError("workout imports require a workout Event")
        if record.domain != DailyDomain.EXERCISE or not isinstance(record.time, InstantTimePoint):
            raise HealthKitImportValidationError("workouts require an exact start time")
        try:
            UUID(entry.source_sample_id)
        except ValueError as exc:
            raise HealthKitImportValidationError("workout source identity must be a UUID") from exc
    elif resource_type == "sleep":
        specific_fields = {"sleep_stage"}
        if (
            not isinstance(record, EventSchemaV1)
            or record.payload.kind != EventKind.SLEEP
            or record.domain != DailyDomain.SLEEP
            or not isinstance(record.time, InstantTimePoint)
            or record.ended_at is None
        ):
            raise HealthKitImportValidationError("sleep imports require an exact sleep interval")
        try:
            UUID(entry.source_sample_id)
        except ValueError as exc:
            raise HealthKitImportValidationError("sleep source identity must be a UUID") from exc
    elif resource_type in {"weight", "resting_heart_rate"}:
        specific_fields = set()
        metric = MetricKey.WEIGHT if resource_type == "weight" else MetricKey.RESTING_HEART_RATE
        if (
            not isinstance(record, ObservationSchemaV1)
            or record.domain != DailyDomain.MEASUREMENTS
            or not isinstance(record.payload.value, MeasurementValueV1)
            or record.payload.value.metric != metric
            or not isinstance(record.time, InstantTimePoint)
        ):
            raise HealthKitImportValidationError(
                f"{resource_type} imports require a matching exact Observation"
            )
        try:
            UUID(entry.source_sample_id)
        except ValueError as exc:
            raise HealthKitImportValidationError(
                f"{resource_type} source identity must be a UUID"
            ) from exc
    elif resource_type == "steps":
        specific_fields = {"aggregation_method_version", "sample_count"}
        if (
            not isinstance(record, ObservationSchemaV1)
            or not isinstance(record.payload.value, StepCountValueV1)
            or record.domain != DailyDomain.EXERCISE
            or not isinstance(record.time, DateOnlyTimePoint)
            or metadata.aggregation_method_version is None
        ):
            raise HealthKitImportValidationError(
                "step imports require a dated daily aggregate and method version"
            )
        aggregate_day = record.time.local_date
        aggregate_timezone = record.time.timezone
        expected_identity = (
            f"daily:{aggregate_day.isoformat()}:{aggregate_timezone}:"
            f"{policy_version}:{installation_id}"
        )
        if entry.source_sample_id != expected_identity:
            raise HealthKitImportValidationError("step aggregate identity is not canonical")
        check_metadata_fields()
        return aggregate_day, aggregate_timezone
    elif resource_type == "heart_rate_summary":
        specific_fields = {
            "aggregation_method_version",
            "sample_count",
            "minimum",
            "maximum",
            "coverage_start",
            "coverage_end",
        }
        if (
            not isinstance(record, ObservationSchemaV1)
            or record.domain != DailyDomain.MEASUREMENTS
            or not isinstance(record.payload.value, MeasurementValueV1)
            or record.payload.value.metric != MetricKey.HEART_RATE_SUMMARY
            or not isinstance(record.time, DateOnlyTimePoint)
            or metadata.aggregation_method_version is None
            or metadata.sample_count is None
            or metadata.minimum is None
            or metadata.maximum is None
            or metadata.coverage_start is None
            or metadata.coverage_end is None
        ):
            raise HealthKitImportValidationError(
                "heart-rate summaries require mean, range, count, coverage, and method version"
            )
        mean = float(record.payload.value.value)
        if not metadata.minimum <= mean <= metadata.maximum:
            raise HealthKitImportValidationError("heart-rate summary mean is outside its range")
        if metadata.minimum < 0 or metadata.maximum < 0:
            raise HealthKitImportValidationError("heart-rate summary values must be nonnegative")
        coverage_start = metadata.coverage_start.astimezone(UTC)
        coverage_end = metadata.coverage_end.astimezone(UTC)
        try:
            day_start, day_end = local_day_bounds(record.time.local_date, record.time.timezone)
        except ValueError as exc:
            raise HealthKitImportValidationError("heart-rate summary date is invalid") from exc
        if coverage_start < day_start or coverage_end > day_end:
            raise HealthKitImportValidationError(
                "heart-rate summary coverage exceeds its local day"
            )
        aggregate_day = record.time.local_date
        aggregate_timezone = record.time.timezone
        expected_identity = (
            f"daily:{aggregate_day.isoformat()}:{aggregate_timezone}:"
            f"{policy_version}:{installation_id}"
        )
        if entry.source_sample_id != expected_identity:
            raise HealthKitImportValidationError("heart-rate aggregate identity is not canonical")
        check_metadata_fields()
        return aggregate_day, aggregate_timezone
    else:
        raise HealthKitImportValidationError("unsupported HealthKit resource type")

    check_metadata_fields()
    try:
        UUID(entry.source_sample_id)
    except ValueError as exc:
        raise HealthKitImportValidationError("sample source identity must be a UUID") from exc
    return None, None


def _result_from_row(row: HealthKitImportBatch, *, replayed: bool) -> HealthKitImportBatchResult:
    return HealthKitImportBatchResult(
        batch_id=row.batch_id,
        replayed=replayed,
        created_count=row.created_count,
        updated_count=row.updated_count,
        unchanged_count=row.unchanged_count,
        tombstoned_count=row.tombstoned_count,
        correction_count=row.correction_count,
        conflict_count=row.conflict_count,
    )


def _daily_record_for_resource(
    owner_id: UUID, resource_type: str, source_sample_id: str, entry: HealthKitImportEntry
) -> tuple[UUID, CreateDailyEntry]:
    object_id = uuid5(owner_id, f"healthkit:{resource_type}:{source_sample_id}")
    metadata = _metadata_for_object(resource_type, source_sample_id, "healthkit-v1", entry.metadata)
    record = entry.record
    if isinstance(record, EventSchemaV1):
        command = CreateDailyEntry(events=(CreateDailyEvent(object_id, record, False, metadata),))
    else:
        command = CreateDailyEntry(
            observations=(CreateDailyObservation(object_id, record, False, metadata),)
        )
    return object_id, command


def _ensure_preference(
    session: Session,
    owner_id: UUID,
    resource_type: str,
    installation_id: UUID,
    source: Source,
) -> HealthKitSourcePreference:
    preference = session.scalar(
        select(HealthKitSourcePreference)
        .where(
            HealthKitSourcePreference.owner_id == owner_id,
            HealthKitSourcePreference.resource_type == resource_type,
        )
        .with_for_update()
    )
    if preference is None:
        preference = HealthKitSourcePreference(
            owner_id=owner_id,
            resource_type=resource_type,
            device_installation_id=installation_id,
            source_id=source.id,
            revision=1,
        )
        session.add(preference)
        session.flush()
        return preference
    return preference


def process_healthkit_import_batch(
    session: Session,
    owner_id: UUID,
    batch: HealthKitImportBatchRequest,
) -> HealthKitImportBatchResult:
    """Validate and apply one batch and receipt in the same owner transaction."""
    aggregate_bounds = {
        entry.source_sample_id: _validate_entry(
            entry, batch.resource_type, batch.device_installation_id, batch.policy_version
        )
        for entry in batch.entries
    }

    canonical_tombstones: list[str] = []
    for tombstone in batch.tombstones:
        if batch.resource_type in AGGREGATE_TYPES:
            suffix = f":{batch.policy_version}:{batch.device_installation_id}"
            if not tombstone.source_sample_id.startswith(
                "daily:"
            ) or not tombstone.source_sample_id.endswith(suffix):
                raise HealthKitImportValidationError("aggregate tombstone identity is invalid")
            date_and_timezone = tombstone.source_sample_id[6 : -len(suffix)]
            try:
                day_text, tombstone_timezone = date_and_timezone.split(":", 1)
                tombstone_day = date.fromisoformat(day_text)
                local_day_bounds(tombstone_day, tombstone_timezone)
            except (ValueError, TypeError) as exc:
                raise HealthKitImportValidationError(
                    "aggregate tombstone identity is invalid"
                ) from exc
            if tombstone.source_sample_id != (
                f"daily:{tombstone_day.isoformat()}:{tombstone_timezone}{suffix}"
            ):
                raise HealthKitImportValidationError("aggregate tombstone identity is invalid")
            canonical_tombstones.append(tombstone.source_sample_id)
        else:
            try:
                canonical_tombstones.append(str(UUID(tombstone.source_sample_id)))
            except ValueError as exc:
                raise HealthKitImportValidationError(
                    "tombstone source identity must be a UUID"
                ) from exc
    canonical_ids = [
        *(_canonical_sample_id(entry.source_sample_id) for entry in batch.entries),
        *canonical_tombstones,
    ]
    if len(canonical_ids) != len(set(canonical_ids)):
        raise HealthKitImportValidationError("batch source identities must be unique")
    batch_hash = _batch_content_hash(batch)
    try:
        with unit_of_work(session):
            owner = session.scalar(select(User).where(User.id == owner_id).with_for_update())
            if owner is None or owner.lifecycle != "active":
                raise DailyNotFound("owner does not exist")
            previous = session.get(HealthKitImportBatch, (owner_id, batch.batch_id))
            if previous is not None:
                if (
                    previous.content_hash != batch_hash
                    or previous.device_installation_id != batch.device_installation_id
                    or previous.resource_type != batch.resource_type
                    or previous.policy_version != batch.policy_version
                ):
                    raise HealthKitImportConflict("batch ID was already used for different content")
                return _result_from_row(previous, replayed=True)

            source = healthkit_source(session, owner_id, batch.device_installation_id)
            counts = {
                "created_count": 0,
                "updated_count": 0,
                "unchanged_count": 0,
                "tombstoned_count": 0,
                "correction_count": 0,
                "conflict_count": 0,
            }
            for entry in batch.entries:
                source_sample_id = _canonical_sample_id(entry.source_sample_id)
                aggregate_day, aggregate_timezone = aggregate_bounds[entry.source_sample_id]
                content_hash = hashlib.sha256(
                    json.dumps(
                        _canonical_entry(entry),
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ).encode("utf-8")
                ).hexdigest()
                identity = session.get(
                    HealthKitImportIdentity,
                    (owner_id, "apple_healthkit", batch.resource_type, source_sample_id),
                )
                if identity is not None and identity.tombstoned_at is not None:
                    counts["unchanged_count"] += 1
                    continue
                object_id, daily_command = _daily_record_for_resource(
                    owner_id,
                    batch.resource_type,
                    source_sample_id,
                    entry.model_copy(update={"source_sample_id": source_sample_id}),
                )
                if identity is None:
                    collision = session.get(HealthObject, object_id)
                    if collision is not None:
                        raise HealthKitImportConflict("source identity is already in use")
                    result = create_daily_entry(
                        session, owner_id, daily_command, write_source=source
                    )
                    imported_object_id = (
                        result.events[0][0].id if result.events else result.observations[0][0].id
                    )
                    is_aggregate = _is_aggregate_record(entry, batch.resource_type)
                    selected = True
                    if is_aggregate:
                        preference = _ensure_preference(
                            session,
                            owner_id,
                            batch.resource_type,
                            batch.device_installation_id,
                            source,
                        )
                        selected = preference.device_installation_id == batch.device_installation_id
                    identity = HealthKitImportIdentity(
                        owner_id=owner_id,
                        platform="apple_healthkit",
                        resource_type=batch.resource_type,
                        source_sample_id=source_sample_id,
                        object_id=imported_object_id,
                        device_installation_id=batch.device_installation_id,
                        content_hash=content_hash,
                        is_aggregate=is_aggregate,
                        aggregate_date=aggregate_day,
                        aggregate_timezone=aggregate_timezone,
                        policy_version=batch.policy_version,
                        analytics_selected=selected,
                    )
                    session.add(identity)
                    counts["created_count"] += 1
                    continue

                if identity.content_hash == content_hash:
                    counts["unchanged_count"] += 1
                    continue

                aggregate = get_daily_item(session, owner_id, identity.object_id)
                obj = aggregate[0]
                if aggregate[2].source_kind != "device" or obj.confirmation_status != "unconfirmed":
                    identity.content_hash = content_hash
                    counts["correction_count"] += 1
                    continue
                record = entry.record
                update_daily_item(
                    session,
                    owner_id,
                    identity.object_id,
                    obj.revision,
                    record,
                    ai_use_allowed=False,
                    metadata=_metadata_for_object(
                        batch.resource_type,
                        source_sample_id,
                        batch.policy_version,
                        entry.metadata,
                    ),
                    write_source=source,
                )
                identity.content_hash = content_hash
                identity.device_installation_id = batch.device_installation_id
                counts["updated_count"] += 1

            for source_sample_id in canonical_tombstones:
                identity = session.get(
                    HealthKitImportIdentity,
                    (owner_id, "apple_healthkit", batch.resource_type, source_sample_id),
                )
                if identity is None or identity.tombstoned_at is not None:
                    counts["unchanged_count"] += 1
                    continue
                aggregate = get_daily_item(session, owner_id, identity.object_id)
                obj = aggregate[0]
                identity.tombstoned_at = datetime.now(UTC)
                if aggregate[2].source_kind != "device" or obj.confirmation_status != "unconfirmed":
                    counts["correction_count"] += 1
                    continue
                archive_daily_item(session, owner_id, identity.object_id, obj.revision)
                counts["tombstoned_count"] += 1

            receipt = HealthKitImportBatch(
                owner_id=owner_id,
                batch_id=batch.batch_id,
                device_installation_id=batch.device_installation_id,
                resource_type=batch.resource_type,
                policy_version=batch.policy_version,
                content_hash=batch_hash,
                **counts,
            )
            session.add(receipt)
            session.flush()
            return _result_from_row(receipt, replayed=False)
    except IntegrityError as exc:
        if not session.in_transaction():
            session.rollback()
        raise HealthKitImportConflict("batch conflicts with accepted import data") from exc
    except (DailyConflict, DailyValidationError) as exc:
        raise HealthKitImportConflict("import conflicts with the current Health record") from exc
    except ValidationError as exc:
        raise HealthKitImportValidationError("normalized import data is invalid") from exc


def get_healthkit_batch_receipt(
    session: Session, owner_id: UUID, batch_id: UUID
) -> HealthKitImportBatchResult | None:
    row = session.get(HealthKitImportBatch, (owner_id, batch_id))
    return _result_from_row(row, replayed=True) if row is not None else None


def get_healthkit_import_status(session: Session, owner_id: UUID) -> HealthKitImportStatusResponse:
    types: list[HealthKitImportTypeStatus] = []
    for resource_type in RESOURCE_TYPES:
        counts = session.execute(
            select(
                func.count().filter(HealthKitImportIdentity.tombstoned_at.is_(None)),
                func.count().filter(HealthKitImportIdentity.tombstoned_at.is_not(None)),
            ).where(
                HealthKitImportIdentity.owner_id == owner_id,
                HealthKitImportIdentity.resource_type == resource_type,
            )
        ).one()
        last_success = session.scalar(
            select(func.max(HealthKitImportBatch.created_at)).where(
                HealthKitImportBatch.owner_id == owner_id,
                HealthKitImportBatch.resource_type == resource_type,
            )
        )
        preference = session.get(HealthKitSourcePreference, (owner_id, resource_type))
        types.append(
            HealthKitImportTypeStatus(
                resource_type=cast(Any, resource_type),
                imported_count=counts[0],
                tombstoned_count=counts[1],
                last_success_at=last_success,
                preferred_installation_id=(
                    preference.device_installation_id if preference is not None else None
                ),
                preference_revision=(preference.revision if preference is not None else None),
            )
        )
    source_rows = session.execute(
        select(Source.external_identifier)
        .where(
            Source.owner_id == owner_id,
            Source.external_namespace == "apple-healthkit",
            Source.external_identifier.is_not(None),
        )
        .order_by(Source.external_identifier)
    ).scalars()
    installations: list[HealthKitSourceInstallation] = []
    for value in source_rows:
        try:
            installation_id = UUID(cast(str, value))
        except ValueError:
            continue
        installations.append(
            HealthKitSourceInstallation(
                device_installation_id=installation_id,
                source_name=f"Apple Health device · {installation_id.hex[:8].upper()}",
            )
        )
    return HealthKitImportStatusResponse(
        server_ingest_enabled=True,
        policy_version="healthkit-v1",
        types=types,
        installations=installations,
    )


def set_healthkit_source_preference(
    session: Session,
    owner_id: UUID,
    request: HealthKitSourcePreferenceRequest,
) -> HealthKitSourcePreferenceResponse:
    try:
        with unit_of_work(session):
            owner = session.scalar(select(User).where(User.id == owner_id).with_for_update())
            if owner is None or owner.lifecycle != "active":
                raise DailyNotFound("owner does not exist")
            source = healthkit_source(session, owner_id, request.device_installation_id)
            has_data = session.scalar(
                select(HealthKitImportIdentity.object_id)
                .where(
                    HealthKitImportIdentity.owner_id == owner_id,
                    HealthKitImportIdentity.resource_type == request.resource_type,
                    HealthKitImportIdentity.device_installation_id
                    == request.device_installation_id,
                    HealthKitImportIdentity.is_aggregate.is_(True),
                )
                .limit(1)
            )
            if has_data is None:
                raise HealthKitImportValidationError(
                    "selected installation has no aggregate data for this type"
                )
            preference = session.scalar(
                select(HealthKitSourcePreference)
                .where(
                    HealthKitSourcePreference.owner_id == owner_id,
                    HealthKitSourcePreference.resource_type == request.resource_type,
                )
                .with_for_update()
            )
            if preference is None:
                if request.expected_revision is not None:
                    raise HealthKitImportConflict("source preference revision is stale")
                preference = HealthKitSourcePreference(
                    owner_id=owner_id,
                    resource_type=request.resource_type,
                    device_installation_id=request.device_installation_id,
                    source_id=source.id,
                    revision=1,
                )
                session.add(preference)
            else:
                if request.expected_revision != preference.revision:
                    raise HealthKitImportConflict("source preference revision is stale")
                if preference.device_installation_id == request.device_installation_id:
                    return HealthKitSourcePreferenceResponse(
                        resource_type=request.resource_type,
                        device_installation_id=preference.device_installation_id,
                        revision=preference.revision,
                    )
                preference.device_installation_id = request.device_installation_id
                preference.source_id = source.id
                preference.revision += 1
            session.execute(
                update(HealthKitImportIdentity)
                .where(
                    HealthKitImportIdentity.owner_id == owner_id,
                    HealthKitImportIdentity.resource_type == request.resource_type,
                    HealthKitImportIdentity.is_aggregate.is_(True),
                )
                .values(
                    analytics_selected=(
                        HealthKitImportIdentity.device_installation_id
                        == request.device_installation_id
                    )
                )
            )
            new_sequence = next_daily_sequence(session, owner_id)
            session.execute(
                delete(DailySnapshotMarker).where(
                    DailySnapshotMarker.owner_id == owner_id,
                    DailySnapshotMarker.daily_sequence != new_sequence,
                )
            )
            session.flush()
            invalidate_analytics(session, owner_id)
            return HealthKitSourcePreferenceResponse(
                resource_type=request.resource_type,
                device_installation_id=preference.device_installation_id,
                revision=preference.revision,
            )
    except IntegrityError as exc:
        if not session.in_transaction():
            session.rollback()
        raise HealthKitImportConflict("source preference could not be saved") from exc
