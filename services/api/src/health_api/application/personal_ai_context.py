"""Health-owned, permission-filtered projection for the Personal AI read contract."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from health_api.application.ai_context_admission import _eligibility_conditions
from health_api.domain.ai import AIResourceType
from health_api.domain.daily import local_day_bounds
from health_api.domain.schemas import (
    DailyTimePoint,
    DateOnlyTimePoint,
    InstantTimePoint,
    ProfileSchemaRegistry,
)
from health_api.integrations.personal_ai_context import (
    DAILY_CATEGORIES,
    PROFILE_CATEGORIES,
    HealthConfirmation,
    HealthContextCategory,
    HealthContextCategoryOption,
    HealthContextFieldSensitivity,
    HealthContextPayload,
    HealthContextPermissionDependency,
    HealthContextPermissionVersion,
    HealthContextReadRequest,
    HealthContextReadResponse,
    HealthContextRecord,
    HealthContextSourceReference,
    HealthResourceType,
    HealthSensitivity,
    HealthSourceKind,
)
from health_api.persistence.models import (
    EventItem,
    HealthObject,
    ObservationItem,
    ProfileItem,
    ProviderIdentity,
    Source,
    User,
)

MAX_CONTEXT_CANDIDATES = 1_000
_PROFILE_CATEGORY_TO_DB = {
    "profile_background": "background",
    "profile_constraints": "constraints",
    "profile_preferences": "preferences",
}
_CATEGORY_RESOURCES: dict[HealthContextCategory, tuple[AIResourceType, ...]] = {
    "measurements": ("observation",),
    "nutrition": ("event",),
    "exercise": ("event", "observation"),
    "sleep": ("event",),
    "symptoms": ("event", "observation"),
}
_ALL_CATEGORIES: tuple[HealthContextCategory, ...] = (
    "profile_background",
    "profile_constraints",
    "profile_preferences",
    "measurements",
    "nutrition",
    "exercise",
    "sleep",
    "symptoms",
)
_CATEGORY_LABELS = {
    "profile_background": "Profile background",
    "profile_constraints": "Profile constraints",
    "profile_preferences": "Profile preferences",
    "measurements": "Measurements",
    "nutrition": "Nutrition",
    "exercise": "Exercise and activity",
    "sleep": "Sleep",
    "symptoms": "Symptoms",
}
_QUALITY_METADATA = {
    "aggregation_method_version": "healthkit_aggregation_method_version",
    "sample_count": "healthkit_sample_count",
    "minimum": "healthkit_minimum",
    "maximum": "healthkit_maximum",
    "coverage_start": "healthkit_coverage_start",
    "coverage_end": "healthkit_coverage_end",
}
_SENSITIVITY: dict[str, HealthSensitivity] = {
    "record": "restricted",
    "notes": "restricted",
    "domain": "restricted",
    "time": "sensitive",
    "interval_end": "sensitive",
    "units": "sensitive",
    "source_kind": "sensitive",
    "confirmation_status": "sensitive",
    "quality": "sensitive",
    "uncertainty": "sensitive",
    "validity": "sensitive",
}


class HealthContextSelectionError(ValueError):
    """Stable domain rejection for unsupported or over-broad read requests."""


def resolve_existing_owner(session: Session, *, issuer: str, subject: str) -> UUID | None:
    """Resolve only an existing active identity; service requests never create owners."""
    identity = session.get(ProviderIdentity, (issuer, subject))
    if identity is None:
        return None
    owner = session.get(User, identity.user_id)
    if owner is None or owner.lifecycle != "active":
        return None
    return owner.id


def _owner_timezone(session: Session, owner_id: UUID) -> ZoneInfo:
    owner = session.get(User, owner_id)
    if owner is None or owner.lifecycle != "active":
        raise HealthContextSelectionError("health_context_owner_unavailable")
    try:
        return ZoneInfo(owner.display_timezone)
    except (ValueError, KeyError) as error:
        raise HealthContextSelectionError("health_context_timezone_invalid") from error


def _category_resources(category: HealthContextCategory) -> tuple[AIResourceType, ...]:
    if category in PROFILE_CATEGORIES:
        return ("profile_item",)
    return _CATEGORY_RESOURCES[category]


def _profile_category(category: HealthContextCategory) -> str:
    try:
        return _PROFILE_CATEGORY_TO_DB[category]
    except KeyError as error:
        raise HealthContextSelectionError("health_context_category_invalid") from error


def _date_window(
    *, timezone: ZoneInfo, start: datetime, end: datetime
) -> tuple[date, datetime, date]:
    """Build conservative date-only and exact-instant bounds for the shared SQL gate."""
    local_start = start.astimezone(timezone)
    local_end = end.astimezone(timezone)
    start_date = local_start.date()
    end_date = local_end.date()
    if local_end.timetz().replace(tzinfo=None) == time.min:
        end_date -= timedelta(days=1)
    try:
        start_at = local_day_bounds(start_date, timezone.key)[0]
    except (OverflowError, ValueError) as error:
        raise HealthContextSelectionError("health_context_window_invalid") from error
    return start_date, max(start_at, start), end_date


def _current_window(now: datetime, timezone: ZoneInfo) -> tuple[date, datetime, date]:
    local_date = now.astimezone(timezone).date()
    try:
        start_at = local_day_bounds(local_date, timezone.key)[0]
    except (OverflowError, ValueError) as error:
        raise HealthContextSelectionError("health_context_window_invalid") from error
    return local_date, start_at, local_date


def _eligibility(
    owner_id: UUID,
    *,
    object_type: AIResourceType,
    as_of: datetime,
    start_date: date,
    start_at: datetime,
    end_date: date,
    category: HealthContextCategory,
) -> list[Any]:
    payload = {
        "profile_item": ProfileItem.payload,
        "event": EventItem.payload,
        "observation": ObservationItem.payload,
    }[object_type]
    domains = (category,) if category in DAILY_CATEGORIES else ()
    return _eligibility_conditions(
        owner_id,
        object_type=object_type,
        payload=payload,
        as_of=as_of,
        start_date=start_date,
        start_at=start_at,
        end_date=end_date,
        domains=domains,
        require_cross_domain=True,
    )


def _query_rows(
    session: Session,
    owner_id: UUID,
    request: HealthContextReadRequest,
    *,
    object_type: AIResourceType,
    as_of: datetime,
    start_date: date,
    start_at: datetime,
    end_date: date,
) -> list[tuple[HealthObject, Any, str]]:
    subtype = cast(
        Any,
        {
            "profile_item": ProfileItem,
            "event": EventItem,
            "observation": ObservationItem,
        }[object_type],
    )
    category = request.category
    if category is None:
        raise HealthContextSelectionError("health_context_category_invalid")
    join_condition = and_(
        subtype.owner_id == HealthObject.owner_id,
        subtype.object_id == HealthObject.id,
    )
    conditions = _eligibility(
        owner_id,
        object_type=object_type,
        as_of=as_of,
        start_date=start_date,
        start_at=start_at,
        end_date=end_date,
        category=category,
    )
    if object_type == "profile_item":
        conditions.append(ProfileItem.category == _profile_category(category))
    if request.entity_refs:
        selected_ids = tuple(reference.object_id for reference in request.entity_refs)
        conditions.append(HealthObject.id.in_(selected_ids))
    statement = (
        select(HealthObject, subtype, Source.source_kind)
        .select_from(HealthObject)
        .join(subtype, join_condition)
        .join(
            Source,
            and_(Source.owner_id == HealthObject.owner_id, Source.id == HealthObject.source_id),
        )
        .where(*conditions)
        .order_by(HealthObject.recorded_at.desc(), HealthObject.id)
        .limit(min(request.max_results + 1, MAX_CONTEXT_CANDIDATES))
    )
    return list(session.execute(statement).all())


def _permission_version_values(
    revision: int, ai_use_allowed: bool, cross_domain_use_allowed: bool
) -> str:
    return (
        f"health-object-v1:r{revision}:ai{int(ai_use_allowed)}:cross{int(cross_domain_use_allowed)}"
    )


def _permission_version(obj: HealthObject) -> str:
    return _permission_version_values(
        obj.revision, obj.ai_use_allowed, obj.cross_domain_use_allowed
    )


def _record_data(object_type: str, subtype: Any) -> dict[str, Any]:
    raw = subtype.payload
    try:
        if object_type == "profile_item":
            model = ProfileSchemaRegistry.get("profile_item", 1)
        elif object_type == "event":
            model = ProfileSchemaRegistry.get("event", 1)
        else:
            model = ProfileSchemaRegistry.get("observation", 1)
        validated = model.model_validate(raw)
        dumped = validated.model_dump(mode="json")
    except Exception as error:
        raise HealthContextSelectionError("health_context_source_invalid") from error
    if not isinstance(dumped, dict):
        raise HealthContextSelectionError("health_context_source_invalid")
    return dumped


def _time_data(object_type: str, subtype: Any) -> DailyTimePoint | None:
    if object_type == "profile_item":
        return None
    if subtype.time_precision == "instant":
        return InstantTimePoint(
            precision="instant",
            occurred_at=subtype.occurred_at,
            timezone=subtype.timezone,
        )
    if subtype.time_precision == "date_only":
        return DateOnlyTimePoint(
            precision="date_only",
            local_date=subtype.local_date,
            timezone=subtype.timezone,
        )
    raise HealthContextSelectionError("health_context_source_invalid")


def _units_for(object_type: str, record: dict[str, Any]) -> dict[str, str]:
    units: dict[str, str] = {}
    if object_type in {"observation", "profile_item"}:
        value = record.get("value")
        if isinstance(value, dict) and isinstance(value.get("unit"), str):
            key = value.get("metric", "value")
            units[str(key)] = value["unit"]
    elif object_type == "event":
        for key in ("energy", "duration", "distance"):
            quantity = record.get(key)
            if isinstance(quantity, dict) and isinstance(quantity.get("unit"), str):
                units[key] = quantity["unit"]
    return units


def _quality(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    result: dict[str, Any] = {}
    for field, source_key in _QUALITY_METADATA.items():
        if source_key in metadata:
            result[field] = metadata[source_key]
    return result


def _content_fingerprint(payload: HealthContextPayload) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _to_record(
    obj: HealthObject,
    subtype: Any,
    source_kind: str,
    request: HealthContextReadRequest,
) -> HealthContextRecord:
    category = request.category
    if category is None:
        raise HealthContextSelectionError("health_context_category_invalid")
    if obj.object_type not in {"profile_item", "event", "observation"}:
        raise HealthContextSelectionError("health_context_source_invalid")
    object_type = cast(HealthResourceType, obj.object_type)
    source_kind = cast(HealthSourceKind, source_kind)
    confirmation_status = cast(HealthConfirmation, obj.confirmation_status)
    raw_record = _record_data(object_type, subtype)
    selected_fields = set(request.fields)
    record = raw_record if "record" in selected_fields else None
    notes = obj.notes if "notes" in selected_fields else None
    time_data = _time_data(object_type, subtype) if "time" in selected_fields else None
    interval_end = (
        getattr(subtype, "ended_at", None)
        if object_type == "event"
        else getattr(subtype, "interval_end", None)
    )
    if "interval_end" not in selected_fields:
        interval_end = None
    quality = _quality(obj.metadata_json) if "quality" in selected_fields else None
    units = _units_for(object_type, raw_record) if "units" in selected_fields else None
    valid_from = obj.valid_from
    valid_to = obj.valid_to
    payload = HealthContextPayload(
        category=category,
        object_type=object_type,
        domain=obj.domain if "domain" in selected_fields else None,
        record=record,
        notes=notes,
        time=time_data,
        interval_end=interval_end,
        units=units,
        source_kind=source_kind if "source_kind" in selected_fields else None,
        confirmation_status=(
            confirmation_status if "confirmation_status" in selected_fields else None
        ),
        quality=quality,
        uncertainty=None,
        validity=(
            {"valid_from": valid_from, "valid_to": valid_to}
            if "validity" in selected_fields
            else None
        ),
    )
    fingerprint = _content_fingerprint(payload)
    reference_id = str(obj.id)
    source_id = str(obj.source_id)
    dependency = HealthContextPermissionDependency(
        permission_id=f"health_context_read:{category}:{object_type}:{obj.id}",
        version=_permission_version(obj),
    )
    labels = tuple(
        HealthContextFieldSensitivity(field=field, sensitivity=_SENSITIVITY[field])
        for field in request.fields
        if field in payload.model_fields_set
    )
    return HealthContextRecord(
        object_id=obj.id,
        object_type=object_type,
        object_revision=obj.revision,
        schema_version=obj.schema_version,
        source_id=obj.source_id,
        source_version=f"health-object-v1:r{obj.revision}:schema-{obj.schema_version}",
        source_kind=source_kind,
        confirmation_status=confirmation_status,
        authority="authoritative",
        observed_at=obj.recorded_at,
        effective_at=obj.valid_from,
        expires_at=obj.valid_to,
        sensitivity="restricted",
        field_sensitivity=labels
        or (HealthContextFieldSensitivity(field="record", sensitivity="restricted"),),
        source_refs=(
            HealthContextSourceReference(
                kind="record", reference_id=reference_id, fingerprint=fingerprint
            ),
            HealthContextSourceReference(
                kind="source", reference_id=source_id, fingerprint=fingerprint
            ),
        ),
        permission_dependencies=(dependency,),
        payload=payload,
    )


def _authorized_category_exists(
    session: Session,
    owner_id: UUID,
    category: HealthContextCategory,
    *,
    as_of: datetime,
    start_date: date,
    start_at: datetime,
    end_date: date,
) -> bool:
    for object_type in _category_resources(category):
        subtype = cast(
            Any,
            {
                "profile_item": ProfileItem,
                "event": EventItem,
                "observation": ObservationItem,
            }[object_type],
        )
        join_condition = and_(
            subtype.owner_id == HealthObject.owner_id,
            subtype.object_id == HealthObject.id,
        )
        conditions = _eligibility(
            owner_id,
            object_type=object_type,
            as_of=as_of,
            start_date=start_date,
            start_at=start_at,
            end_date=end_date,
            category=category,
        )
        if object_type == "profile_item":
            conditions.append(ProfileItem.category == _profile_category(category))
        exists = session.scalar(
            select(HealthObject.id)
            .select_from(HealthObject)
            .join(subtype, join_condition)
            .where(*conditions)
            .limit(1)
        )
        if exists is not None:
            return True
    return False


def _catalog(
    session: Session, owner_id: UUID, *, now: datetime, timezone: ZoneInfo
) -> tuple[HealthContextCategoryOption, ...]:
    start = now - timedelta(days=90)
    start_date, start_at, end_date = _date_window(timezone=timezone, start=start, end=now)
    options: list[HealthContextCategoryOption] = []
    for category in _ALL_CATEGORIES:
        if _authorized_category_exists(
            session,
            owner_id,
            category,
            as_of=now,
            start_date=start_date,
            start_at=start_at,
            end_date=end_date,
        ):
            options.append(
                HealthContextCategoryOption(
                    category=category,
                    display_name=_CATEGORY_LABELS[category],
                )
            )
    return tuple(options)


def _verify_permission(
    session: Session,
    owner_id: UUID,
    request: HealthContextReadRequest,
    *,
    now: datetime,
    timezone: ZoneInfo,
) -> tuple[HealthContextPermissionVersion, ...]:
    category = request.category
    if category is None:
        raise HealthContextSelectionError("health_context_category_invalid")
    reference = request.entity_refs[0]
    start = now - timedelta(days=90)
    start_date, start_at, end_date = _date_window(timezone=timezone, start=start, end=now)
    object_type = reference.object_type
    subtype = cast(
        Any,
        {"profile_item": ProfileItem, "event": EventItem, "observation": ObservationItem}[
            object_type
        ],
    )
    join_condition = and_(
        subtype.owner_id == HealthObject.owner_id, subtype.object_id == HealthObject.id
    )
    conditions = _eligibility(
        owner_id,
        object_type=object_type,
        as_of=now,
        start_date=start_date,
        start_at=start_at,
        end_date=end_date,
        category=category,
    )
    conditions.append(HealthObject.id == reference.object_id)
    if object_type == "profile_item":
        conditions.append(ProfileItem.category == _profile_category(category))
    row = session.execute(
        select(
            HealthObject.id,
            HealthObject.revision,
            HealthObject.ai_use_allowed,
            HealthObject.cross_domain_use_allowed,
        )
        .select_from(HealthObject)
        .join(subtype, join_condition)
        .where(*conditions)
        .limit(1)
    ).first()
    if row is None:
        return ()
    return (
        HealthContextPermissionVersion(
            object_id=row.id,
            version=_permission_version_values(
                row.revision, row.ai_use_allowed, row.cross_domain_use_allowed
            ),
        ),
    )


def _read_rows(
    session: Session,
    owner_id: UUID,
    request: HealthContextReadRequest,
    *,
    now: datetime,
    timezone: ZoneInfo,
) -> tuple[tuple[HealthContextRecord, ...], bool]:
    assert request.category is not None
    if request.operation == "profile":
        start_date, start_at, end_date = _current_window(now, timezone)
        as_of = now
    else:
        assert request.window_start is not None and request.window_end is not None
        start_date, start_at, end_date = _date_window(
            timezone=timezone,
            start=request.window_start,
            end=request.window_end,
        )
        as_of = request.window_end

    rows: list[tuple[HealthObject, Any, str]] = []
    for object_type in _category_resources(request.category):
        if request.entity_refs and object_type not in {
            reference.object_type for reference in request.entity_refs
        }:
            continue
        rows.extend(
            _query_rows(
                session,
                owner_id,
                request,
                object_type=object_type,
                as_of=as_of,
                start_date=start_date,
                start_at=start_at,
                end_date=end_date,
            )
        )
    rows.sort(key=lambda row: (row[0].recorded_at, str(row[0].id)), reverse=True)
    truncated = len(rows) > request.max_results
    return tuple(
        _to_record(obj, subtype, source_kind, request)
        for obj, subtype, source_kind in rows[: request.max_results]
    ), truncated


def read_personal_ai_health_context(
    session: Session,
    owner_id: UUID,
    request: HealthContextReadRequest,
    *,
    now: datetime | None = None,
) -> HealthContextReadResponse:
    """Read only authorized current Health data into a versioned, bounded projection."""
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    timezone = _owner_timezone(session, owner_id)
    if request.window_end is not None and request.window_end > current_time:
        raise HealthContextSelectionError("health_context_window_future")
    if request.operation == "catalog":
        response = HealthContextReadResponse(
            operation="catalog",
            categories=_catalog(session, owner_id, now=current_time, timezone=timezone),
        )
    elif request.operation == "verify":
        response = HealthContextReadResponse(
            operation="verify",
            permission_versions=_verify_permission(
                session, owner_id, request, now=current_time, timezone=timezone
            ),
        )
    else:
        records, truncated = _read_rows(
            session,
            owner_id,
            request,
            now=current_time,
            timezone=timezone,
        )
        response = HealthContextReadResponse(
            operation=request.operation,
            items=records,
            truncated=truncated,
        )
    while len(response.model_dump_json().encode("utf-8")) > request.max_bytes:
        if not response.items:
            raise HealthContextSelectionError("health_context_response_limit_exceeded")
        response = response.model_copy(update={"items": response.items[:-1], "truncated": True})
    return response
