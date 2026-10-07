"""Typed owner-scoped Event, Observation, and Today API routes."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from health_api.api.dependencies import get_current_owner, get_session
from health_api.api.errors import APIError
from health_api.api.schemas import (
    DailyEntryCreateRequest,
    DailyEntryCreateResponse,
    DailyEventCreateRequest,
    DailyEventListResponse,
    DailyEventResponse,
    DailyEventUpdateRequest,
    DailyHistoryEntry,
    DailyHistoryResponse,
    DailyItemResponse,
    DailyObservationCreateRequest,
    DailyObservationListResponse,
    DailyObservationResponse,
    DailyObservationUpdateRequest,
    ErrorResponse,
    OccurrenceResponse,
    ProfileContextReference,
    TodayContextSummary,
    TodayResponse,
)
from health_api.application.daily_service import (
    CreateDailyEntry,
    CreateDailyEvent,
    CreateDailyLink,
    CreateDailyObservation,
    DailyAggregate,
    archive_daily_item,
    create_daily_entry,
    get_daily_item,
    list_daily_history,
    list_daily_items,
    update_daily_item,
)
from health_api.application.errors import DailyNotFound
from health_api.application.planning_service import load_today_planning
from health_api.application.today_service import (
    healthkit_preferred_installations,
    is_today_snapshot_boundary,
    load_today_snapshot,
    owner_today_settings,
    summarize_today_snapshot,
)
from health_api.domain.schemas import (
    EventSchemaV1,
    InstantTimePoint,
    ObservationSchemaV1,
    ProfileMetadata,
    validate_iana_timezone,
)
from health_api.persistence.models import (
    EventItem,
    HealthObject,
    HealthObjectRevision,
    ObservationItem,
    Source,
)

router = APIRouter(tags=["daily"])

COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication is required or invalid."},
    413: {
        "model": ErrorResponse,
        "description": "Request body exceeds the 65,536 byte limit.",
    },
    422: {"model": ErrorResponse, "description": "Request validation failed."},
    503: {"model": ErrorResponse, "description": "Health storage is unavailable."},
}
NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Daily entry was not found."}
}
CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "Revision or ID conflict."}
}

type ResourceCursorKey = tuple[datetime, UUID]
type TodayCursorKey = tuple[str, int, str, str]
type DailyRecord = EventSchemaV1 | ObservationSchemaV1


def _owner_binding(owner_id: UUID) -> str:
    return hashlib.sha256(owner_id.bytes).hexdigest()


def _invalid_cursor() -> APIError:
    return APIError(422, "invalid_cursor", "Pagination cursor is invalid for these filters.")


def _encode_resource_cursor(
    owner_id: UUID,
    object_type: str,
    from_date: date | None,
    to_date: date | None,
    timezone: str,
    after: ResourceCursorKey,
) -> str:
    payload = {
        "v": 1,
        "owner": _owner_binding(owner_id),
        "object_type": object_type,
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "timezone": timezone,
        "created_at": after[0].isoformat(),
        "id": str(after[1]),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_resource_cursor(
    value: str,
    owner_id: UUID,
    object_type: str,
    from_date: date | None,
    to_date: date | None,
    timezone: str,
) -> ResourceCursorKey:
    try:
        if len(value) > 2048:
            raise ValueError
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(raw)
        if set(payload) != {
            "v",
            "owner",
            "object_type",
            "from_date",
            "to_date",
            "timezone",
            "created_at",
            "id",
        }:
            raise ValueError
        if (
            payload["v"] != 1
            or payload["owner"] != _owner_binding(owner_id)
            or payload["object_type"] != object_type
            or payload["from_date"] != (from_date.isoformat() if from_date else None)
            or payload["to_date"] != (to_date.isoformat() if to_date else None)
            or payload["timezone"] != timezone
        ):
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError
        return created_at.astimezone(UTC), UUID(payload["id"])
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid_cursor() from exc


def _time_point_from_fields(
    precision: str,
    timezone: str,
    occurred_at: datetime | None,
    local_date: date | None,
) -> dict[str, object]:
    if precision == "instant":
        return {"precision": precision, "occurred_at": occurred_at, "timezone": timezone}
    return {"precision": precision, "local_date": local_date, "timezone": timezone}


def _common_envelope(obj: HealthObject, source: Source) -> dict[str, object]:
    try:
        metadata = ProfileMetadata.model_validate(obj.metadata_json)
    except ValidationError as exc:
        raise RuntimeError("stored daily envelope metadata is invalid") from exc
    return {
        "id": obj.id,
        "domain": obj.domain,
        "status": obj.status,
        "title": obj.title,
        "valid_from": obj.valid_from,
        "valid_to": obj.valid_to,
        "recorded_at": obj.recorded_at,
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
        "source": {"id": source.id, "kind": source.source_kind, "name": source.display_name},
        "confirmation_status": obj.confirmation_status,
        "schema_version": obj.schema_version,
        "revision": obj.revision,
        "notes": obj.notes,
        "metadata": metadata,
        "permissions": {
            "ai_use_allowed": obj.ai_use_allowed,
            "cross_domain_use_allowed": obj.cross_domain_use_allowed,
        },
    }


def _event_response(
    aggregate: tuple[HealthObject, EventItem, Source, tuple[UUID, ...]],
) -> DailyEventResponse:
    obj, event_row, source, linked_ids = aggregate
    try:
        event = EventSchemaV1.model_validate(
            {
                "domain": obj.domain,
                "time": _time_point_from_fields(
                    event_row.time_precision,
                    event_row.timezone,
                    event_row.occurred_at,
                    event_row.local_date,
                ),
                "ended_at": event_row.ended_at,
                "payload": event_row.payload,
                "notes": obj.notes,
            }
        )
    except ValidationError as exc:
        raise RuntimeError("stored Event data is invalid") from exc
    return DailyEventResponse.model_validate(
        {
            **_common_envelope(obj, source),
            "object_type": "event",
            "event": event,
            "linked_observation_ids": list(linked_ids),
        }
    )


def _observation_response(
    aggregate: tuple[HealthObject, ObservationItem, Source],
) -> DailyObservationResponse:
    obj, observation_row, source = aggregate
    try:
        observation = ObservationSchemaV1.model_validate(
            {
                "domain": obj.domain,
                "time": _time_point_from_fields(
                    observation_row.time_precision,
                    observation_row.timezone,
                    observation_row.observed_at,
                    observation_row.local_date,
                ),
                "interval_end": observation_row.interval_end,
                "payload": observation_row.payload,
                "notes": obj.notes,
            }
        )
    except ValidationError as exc:
        raise RuntimeError("stored Observation data is invalid") from exc
    return DailyObservationResponse.model_validate(
        {
            **_common_envelope(obj, source),
            "object_type": "observation",
            "observation": observation,
        }
    )


def _aggregate_response(aggregate: DailyAggregate) -> DailyItemResponse:
    if isinstance(aggregate[1], EventItem):
        return _event_response(aggregate)
    return _observation_response(aggregate)


def _revision_response(revision: HealthObjectRevision) -> DailyItemResponse:
    snapshot: dict[str, Any] = revision.snapshot
    if snapshot.get("object_type") == "event":
        try:
            event = EventSchemaV1.model_validate(
                {
                    "domain": snapshot["domain"],
                    "time": snapshot["time"],
                    "ended_at": snapshot["ended_at"],
                    "payload": snapshot["payload"],
                    "notes": snapshot["notes"],
                }
            )
            return DailyEventResponse.model_validate(
                {
                    **{
                        key: value
                        for key, value in snapshot.items()
                        if key not in {"time", "ended_at", "payload", "linked_observation_ids"}
                    },
                    "id": revision.object_id,
                    "object_type": "event",
                    "event": event,
                    "linked_observation_ids": snapshot.get("linked_observation_ids", []),
                }
            )
        except (ValidationError, KeyError) as exc:
            raise RuntimeError("stored Event history is invalid") from exc
    try:
        observation = ObservationSchemaV1.model_validate(
            {
                "domain": snapshot["domain"],
                "time": snapshot["time"],
                "interval_end": snapshot["interval_end"],
                "payload": snapshot["payload"],
                "notes": snapshot["notes"],
            }
        )
        return DailyObservationResponse.model_validate(
            {
                **{
                    key: value
                    for key, value in snapshot.items()
                    if key not in {"time", "interval_end", "payload"}
                },
                "id": revision.object_id,
                "object_type": "observation",
                "observation": observation,
            }
        )
    except (ValidationError, KeyError) as exc:
        raise RuntimeError("stored Observation history is invalid") from exc


def _entry_history(revision: HealthObjectRevision) -> DailyHistoryEntry:
    return DailyHistoryEntry(
        revision=revision.revision,
        recorded_at=revision.recorded_at,
        actor_kind="user",
        reason=cast(Literal["create", "update", "archive"], revision.reason),
        proposal_id=revision.proposal_id,
        snapshot=_revision_response(revision),
    )


def _create_command(body: DailyEntryCreateRequest) -> CreateDailyEntry:
    return CreateDailyEntry(
        events=tuple(
            CreateDailyEvent(item.id, item.event, item.ai_use_allowed) for item in body.events
        ),
        observations=tuple(
            CreateDailyObservation(item.id, item.observation, item.ai_use_allowed)
            for item in body.observations
        ),
        links=tuple(
            CreateDailyLink(link.event_id, link.observation_id, link.role) for link in body.links
        ),
    )


def _validate_list_range(
    from_date: date | None,
    to_date: date | None,
    timezone: str | None,
    display_timezone: str,
) -> str:
    if (from_date is None) != (to_date is None):
        raise APIError(422, "invalid_time_range", "Both date range bounds are required.")
    if (
        from_date is not None
        and to_date is not None
        and (to_date < from_date or to_date == date.max or (to_date - from_date).days + 1 > 366)
    ):
        raise APIError(422, "invalid_time_range", "Date range must span at most 366 days.")
    try:
        return validate_iana_timezone(timezone or display_timezone)
    except ValueError as exc:
        raise APIError(422, "invalid_timezone", "Timezone must be a valid IANA name.") from exc


def _list_daily_resource(
    *,
    object_type: str,
    owner_id: UUID,
    session: Session,
    limit: int,
    cursor: str | None,
    from_date: date | None,
    to_date: date | None,
    timezone: str | None,
) -> tuple[list[DailyItemResponse], str | None]:
    _, display_timezone = owner_today_settings(session, owner_id)
    effective_timezone = _validate_list_range(from_date, to_date, timezone, display_timezone)
    after = (
        _decode_resource_cursor(
            cursor,
            owner_id,
            object_type,
            from_date,
            to_date,
            effective_timezone,
        )
        if cursor
        else None
    )
    results = list_daily_items(
        session,
        owner_id,
        object_type,
        limit + 1,
        after,
        from_date,
        to_date,
        effective_timezone,
    )
    has_more = len(results) > limit
    page = results[:limit]
    next_cursor = None
    if has_more and page:
        created_at = page[-1][0].created_at
        next_cursor = _encode_resource_cursor(
            owner_id,
            object_type,
            from_date,
            to_date,
            effective_timezone,
            (created_at.astimezone(UTC), page[-1][0].id),
        )
    return [_aggregate_response(item) for item in page], next_cursor


@router.get(
    "/events",
    response_model=DailyEventListResponse,
    operation_id="listEvents",
    responses=COMMON_ERROR_RESPONSES,
)
def list_events(
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    timezone: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> DailyEventListResponse:
    items, next_cursor = _list_daily_resource(
        object_type="event",
        owner_id=owner_id,
        session=session,
        limit=limit,
        cursor=cursor,
        from_date=from_date,
        to_date=to_date,
        timezone=timezone,
    )
    return DailyEventListResponse(
        items=cast(list[DailyEventResponse], items), next_cursor=next_cursor
    )


@router.post(
    "/events",
    response_model=DailyEventResponse,
    status_code=201,
    operation_id="createEvent",
    responses={
        **COMMON_ERROR_RESPONSES,
        **CONFLICT_RESPONSE,
        200: {
            "model": DailyEventResponse,
            "description": "Idempotent create retry returns the existing Event.",
        },
    },
)
def create_event(
    body: DailyEventCreateRequest,
    response: Response,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> DailyEventResponse:
    result = create_daily_entry(
        session,
        owner_id,
        CreateDailyEntry(events=(CreateDailyEvent(body.id, body.event, body.ai_use_allowed),)),
    )
    response.status_code = 201 if result.created else 200
    return _event_response(result.events[0])


@router.get(
    "/events/{event_id}",
    response_model=DailyEventResponse,
    operation_id="getEvent",
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)
def get_event(
    event_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> DailyEventResponse:
    aggregate = get_daily_item(session, owner_id, event_id)
    if not isinstance(aggregate[1], EventItem):
        raise DailyNotFound
    return _event_response(aggregate)


@router.get(
    "/events/{event_id}/history",
    response_model=DailyHistoryResponse,
    operation_id="listEventHistory",
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)
def get_event_history(
    event_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    revision: Annotated[int | None, Query(ge=1)] = None,
) -> DailyHistoryResponse:
    aggregate = get_daily_item(session, owner_id, event_id)
    if not isinstance(aggregate[1], EventItem):
        raise DailyNotFound
    return _history_response(
        session, owner_id, event_id, after_revision, limit, exact_revision=revision
    )


@router.patch(
    "/events/{event_id}",
    response_model=DailyEventResponse,
    operation_id="updateEvent",
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE},
)
def patch_event(
    event_id: UUID,
    body: DailyEventUpdateRequest,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> DailyEventResponse:
    aggregate = update_daily_item(
        session,
        owner_id,
        event_id,
        body.expected_revision,
        body.event,
        body.ai_use_allowed,
    )
    if not isinstance(aggregate[1], EventItem):
        raise DailyNotFound
    return _event_response(aggregate)


@router.delete(
    "/events/{event_id}",
    response_model=DailyEventResponse,
    operation_id="archiveEvent",
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE},
)
def delete_event(
    event_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    expected_revision: Annotated[int, Query(ge=1)],
) -> DailyEventResponse:
    aggregate = archive_daily_item(
        session, owner_id, event_id, expected_revision, expected_object_type="event"
    )
    if not isinstance(aggregate[1], EventItem):
        raise DailyNotFound
    return _event_response(aggregate)


@router.get(
    "/observations",
    response_model=DailyObservationListResponse,
    operation_id="listObservations",
    responses=COMMON_ERROR_RESPONSES,
)
def list_observations(
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    timezone: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> DailyObservationListResponse:
    items, next_cursor = _list_daily_resource(
        object_type="observation",
        owner_id=owner_id,
        session=session,
        limit=limit,
        cursor=cursor,
        from_date=from_date,
        to_date=to_date,
        timezone=timezone,
    )
    return DailyObservationListResponse(
        items=cast(list[DailyObservationResponse], items), next_cursor=next_cursor
    )


@router.post(
    "/observations",
    response_model=DailyObservationResponse,
    status_code=201,
    operation_id="createObservation",
    responses={
        **COMMON_ERROR_RESPONSES,
        **CONFLICT_RESPONSE,
        200: {
            "model": DailyObservationResponse,
            "description": "Idempotent create retry returns the existing Observation.",
        },
    },
)
def create_observation(
    body: DailyObservationCreateRequest,
    response: Response,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> DailyObservationResponse:
    result = create_daily_entry(
        session,
        owner_id,
        CreateDailyEntry(
            observations=(CreateDailyObservation(body.id, body.observation, body.ai_use_allowed),)
        ),
    )
    response.status_code = 201 if result.created else 200
    return _observation_response(result.observations[0])


@router.get(
    "/observations/{observation_id}",
    response_model=DailyObservationResponse,
    operation_id="getObservation",
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)
def get_observation(
    observation_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> DailyObservationResponse:
    aggregate = get_daily_item(session, owner_id, observation_id)
    if not isinstance(aggregate[1], ObservationItem):
        raise DailyNotFound
    return _observation_response(aggregate)


@router.get(
    "/observations/{observation_id}/history",
    response_model=DailyHistoryResponse,
    operation_id="listObservationHistory",
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)
def get_observation_history(
    observation_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    revision: Annotated[int | None, Query(ge=1)] = None,
) -> DailyHistoryResponse:
    aggregate = get_daily_item(session, owner_id, observation_id)
    if not isinstance(aggregate[1], ObservationItem):
        raise DailyNotFound
    return _history_response(
        session, owner_id, observation_id, after_revision, limit, exact_revision=revision
    )


@router.patch(
    "/observations/{observation_id}",
    response_model=DailyObservationResponse,
    operation_id="updateObservation",
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE},
)
def patch_observation(
    observation_id: UUID,
    body: DailyObservationUpdateRequest,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> DailyObservationResponse:
    aggregate = update_daily_item(
        session,
        owner_id,
        observation_id,
        body.expected_revision,
        body.observation,
        body.ai_use_allowed,
    )
    if not isinstance(aggregate[1], ObservationItem):
        raise DailyNotFound
    return _observation_response(aggregate)


@router.delete(
    "/observations/{observation_id}",
    response_model=DailyObservationResponse,
    operation_id="archiveObservation",
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE},
)
def delete_observation(
    observation_id: UUID,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    expected_revision: Annotated[int, Query(ge=1)],
) -> DailyObservationResponse:
    aggregate = archive_daily_item(
        session, owner_id, observation_id, expected_revision, expected_object_type="observation"
    )
    if not isinstance(aggregate[1], ObservationItem):
        raise DailyNotFound
    return _observation_response(aggregate)


def _history_response(
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    after_revision: int,
    limit: int,
    *,
    exact_revision: int | None = None,
) -> DailyHistoryResponse:
    revisions = list_daily_history(
        session,
        owner_id,
        object_id,
        after_revision,
        limit + 1,
        exact_revision=exact_revision,
    )
    has_more = len(revisions) > limit
    page = revisions[:limit]
    entries = [_entry_history(revision) for revision in page]
    next_revision = (
        entries[-1].revision if has_more and entries and exact_revision is None else None
    )
    return DailyHistoryResponse(items=entries, next_after_revision=next_revision)


@router.post(
    "/daily-entries",
    response_model=DailyEntryCreateResponse,
    status_code=201,
    operation_id="createDailyEntry",
    responses={
        **COMMON_ERROR_RESPONSES,
        **CONFLICT_RESPONSE,
        200: {
            "model": DailyEntryCreateResponse,
            "description": "Idempotent create retry returns the existing entries.",
        },
    },
)
def create_compound_daily_entry(
    body: DailyEntryCreateRequest,
    response: Response,
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> DailyEntryCreateResponse:
    result = create_daily_entry(session, owner_id, _create_command(body))
    response.status_code = 201 if result.created else 200
    return DailyEntryCreateResponse(
        events=[_event_response(item) for item in result.events],
        observations=[_observation_response(item) for item in result.observations],
        created=result.created,
    )


def _today_key(item: DailyItemResponse, timezone: str) -> TodayCursorKey:
    record: DailyRecord = item.event if isinstance(item, DailyEventResponse) else item.observation
    if isinstance(record.time, InstantTimePoint):
        day = record.time.occurred_at.astimezone(ZoneInfo(timezone)).date().isoformat()
        return day, 1, record.time.occurred_at.astimezone(UTC).isoformat(), str(item.id)
    return record.time.local_date.isoformat(), 0, "", str(item.id)


def _encode_today_cursor(
    owner_id: UUID,
    local_date: date,
    timezone: str,
    as_of_sequence: int,
    after: TodayCursorKey,
) -> str:
    payload = {
        "v": 1,
        "owner": _owner_binding(owner_id),
        "date": local_date.isoformat(),
        "timezone": timezone,
        "as_of_sequence": as_of_sequence,
        "after": list(after),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_today_cursor(
    value: str,
    owner_id: UUID,
    local_date: date,
    timezone: str,
    current_sequence: int,
) -> tuple[int, TodayCursorKey]:
    try:
        if len(value) > 2048:
            raise ValueError
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(raw)
        if set(payload) != {"v", "owner", "date", "timezone", "as_of_sequence", "after"}:
            raise ValueError
        after = payload["after"]
        if (
            payload["v"] != 1
            or payload["owner"] != _owner_binding(owner_id)
            or payload["date"] != local_date.isoformat()
            or payload["timezone"] != timezone
            or type(payload["as_of_sequence"]) is not int
            or payload["as_of_sequence"] < 0
            or payload["as_of_sequence"] > current_sequence
            or not isinstance(after, list)
            or len(after) != 4
            or not isinstance(after[0], str)
            or type(after[1]) is not int
            or after[1] not in (0, 1)
            or not isinstance(after[2], str)
            or not isinstance(after[3], str)
        ):
            raise ValueError
        date.fromisoformat(after[0])
        UUID(after[3])
        if after[1] == 1:
            exact_time = datetime.fromisoformat(after[2])
            if exact_time.tzinfo is None or exact_time.utcoffset() is None:
                raise ValueError
        elif after[2] != "":
            raise ValueError
        return payload["as_of_sequence"], (after[0], after[1], after[2], after[3])
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _invalid_cursor() from exc


@router.get(
    "/today",
    response_model=TodayResponse,
    operation_id="getToday",
    responses={
        **COMMON_ERROR_RESPONSES,
        422: {
            "model": ErrorResponse,
            "description": "Invalid date, timezone, cursor, or bounded snapshot.",
        },
    },
    description=(
        "Returns sparse summaries and a stable timeline for one local calendar day. "
        "The first page carries Profile context references; continuation pages preserve the "
        "daily snapshot sequence and return no duplicate context references. Date-only entries "
        "sort after timed entries on the same day by stable ID, without acquiring an instant."
    ),
)
def get_today(
    owner_id: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    requested_date: Annotated[date | None, Query(alias="date")] = None,
    timezone: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
) -> TodayResponse:
    current_sequence, display_timezone = owner_today_settings(session, owner_id, lock_for_read=True)
    try:
        effective_timezone = validate_iana_timezone(timezone or display_timezone)
    except ValueError as exc:
        raise APIError(422, "invalid_timezone", "Timezone must be a valid IANA name.") from exc
    effective_date = requested_date or datetime.now(ZoneInfo(effective_timezone)).date()
    if effective_date == date.max:
        raise APIError(422, "invalid_date", "Date cannot be represented as a calendar day.")
    if cursor:
        as_of_sequence, after = _decode_today_cursor(
            cursor, owner_id, effective_date, effective_timezone, current_sequence
        )
        if not is_today_snapshot_boundary(session, owner_id, as_of_sequence):
            raise _invalid_cursor()
    else:
        as_of_sequence, after = current_sequence, None

    snapshot = load_today_snapshot(
        session,
        owner_id,
        effective_date,
        effective_timezone,
        as_of_sequence,
        include_profile_context=cursor is None,
    )
    snapshot_items = [_revision_response(revision) for revision in snapshot.revisions]
    snapshot_items.sort(key=lambda item: _today_key(item, effective_timezone), reverse=True)
    items = snapshot_items
    if after is not None:
        items = [item for item in items if _today_key(item, effective_timezone) < after]
    has_more = len(items) > limit
    page = items[:limit]
    next_cursor = None
    if has_more and page:
        next_cursor = _encode_today_cursor(
            owner_id,
            effective_date,
            effective_timezone,
            as_of_sequence,
            _today_key(page[-1], effective_timezone),
        )

    summaries = summarize_today_snapshot(
        snapshot.revisions,
        effective_date,
        effective_timezone,
        healthkit_preferred_installations(session, owner_id),
    )
    plan_items, active_contexts = (
        load_today_planning(session, owner_id, effective_date, effective_timezone)
        if cursor is None
        else ([], [])
    )
    return TodayResponse(
        date=effective_date,
        timezone=effective_timezone,
        as_of_sequence=as_of_sequence,
        items=page,
        summaries=summaries,
        profile_context_refs=[
            ProfileContextReference(id=profile_id, title=title)
            for profile_id, title in snapshot.profile_context
        ],
        profile_context_truncated=snapshot.profile_context_truncated,
        includes_profile_context=cursor is None,
        plan_items=[OccurrenceResponse.model_validate(item) for item in plan_items],
        active_contexts=[TodayContextSummary.model_validate(item) for item in active_contexts],
        next_cursor=next_cursor,
    )
