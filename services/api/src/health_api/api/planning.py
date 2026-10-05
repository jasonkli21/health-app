"""Typed routes for goals, regimens, plans, contexts, and tracker definitions."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from health_api.api.dependencies import get_current_owner, get_session
from health_api.api.errors import APIError
from health_api.api.schemas import (
    ContextCreateRequest,
    ContextResponse,
    ContextUpdateRequest,
    ErrorResponse,
    GoalCreateRequest,
    GoalResponse,
    GoalUpdateRequest,
    LifecycleUpdateRequest,
    OccurrenceActionRequest,
    OccurrenceActionResponse,
    OccurrenceHistoryEntry,
    OccurrenceHistoryResponse,
    OccurrenceListResponse,
    OccurrenceResponse,
    PlanCreateRequest,
    PlanningHistoryEntry,
    PlanningHistoryResponse,
    PlanningItemResponse,
    PlanningListResponse,
    PlanOrderRequest,
    PlanResponse,
    PlanUpdateRequest,
    RegimenCreateRequest,
    RegimenResponse,
    RegimenUpdateRequest,
    ScheduleEditRequest,
    ScheduleResponse,
    TrackerCreateRequest,
    TrackerResponse,
    TrackerSchemaVersionListResponse,
    TrackerSchemaVersionResponse,
    TrackerUpdateRequest,
)
from health_api.application.planning_service import (
    PlanningAggregate,
    PlanningKind,
    archive_planning_resource,
    create_planning_resource,
    get_planning_resource,
    get_planning_schedule,
    list_occurrence_history,
    list_planning_history,
    list_planning_occurrences,
    list_planning_resources,
    record_occurrence_action,
    reorder_plan_items,
    set_planning_schedule,
    transition_planning_resource,
    update_planning_resource,
)
from health_api.domain.planning import (
    ContextLifecycle,
    GoalLifecycle,
    PlanLifecycle,
    RegimenLifecycle,
    TrackerDefinitionV1,
)
from health_api.persistence.models import TrackerSchemaVersion

router = APIRouter(tags=["planning"])
COMMON_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication is required or invalid."},
    413: {"model": ErrorResponse, "description": "Request body exceeds the configured limit."},
    422: {"model": ErrorResponse, "description": "Planning request is invalid."},
    503: {"model": ErrorResponse, "description": "Planning storage is unavailable."},
}
_TYPE_NAME = {
    "goal": "goal",
    "regimen": "regimen",
    "plan": "plan",
    "context": "context",
    "tracker_definition": "definition",
}


def _owner_binding(owner_id: UUID) -> str:
    return hashlib.sha256(owner_id.bytes).hexdigest()


def _encode_cursor(
    owner_id: UUID, kind: str, lifecycle: str | None, row: PlanningAggregate, archived: bool = False
) -> str:
    obj = row[0]
    payload = {
        "v": 1,
        "owner": _owner_binding(owner_id),
        "kind": kind,
        "lifecycle": lifecycle,
        "archived": archived,
        "created_at": obj.created_at.isoformat(),
        "id": str(obj.id),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(
    value: str, owner_id: UUID, kind: str, lifecycle: str | None, archived: bool = False
) -> tuple[datetime, UUID]:
    try:
        if len(value) > 2048:
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
        if set(payload) != {"v", "owner", "kind", "lifecycle", "archived", "created_at", "id"}:
            raise ValueError
        if (
            payload["v"] != 1
            or payload["owner"] != _owner_binding(owner_id)
            or payload["kind"] != kind
            or payload["lifecycle"] != lifecycle
            or payload["archived"] is not archived
        ):
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError
        return created_at.astimezone(UTC), UUID(payload["id"])
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise APIError(
            422, "invalid_cursor", "Pagination cursor is invalid for these filters."
        ) from exc


def resource_response(aggregate: PlanningAggregate) -> dict[str, Any]:
    obj, resource, source = aggregate
    data: dict[str, Any] = {
        "id": obj.id,
        "object_type": resource.resource_kind,
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
        "ai_use_allowed": obj.ai_use_allowed,
        "cross_domain_use_allowed": obj.cross_domain_use_allowed,
        "lifecycle": resource.lifecycle if obj.status == "active" else "archived",
    }
    if resource.resource_kind == "tracker_definition":
        data["current_schema_version"] = resource.current_schema_version
        data["definition"] = resource.payload
    else:
        data[_TYPE_NAME[resource.resource_kind]] = resource.payload
    return data


def _typed_response[T: BaseModel](aggregate: PlanningAggregate, response_type: type[T]) -> T:
    try:
        return response_type.model_validate(resource_response(aggregate))
    except ValidationError as exc:
        raise RuntimeError("stored planning resource is invalid") from exc


def _list(
    session: Session,
    owner_id: UUID,
    kind: PlanningKind,
    limit: int,
    lifecycle: str | None,
    cursor: str | None,
    response_type: type[BaseModel],
    archived: bool = False,
) -> PlanningListResponse:
    after = _decode_cursor(cursor, owner_id, kind, lifecycle, archived) if cursor else None
    rows = list_planning_resources(session, owner_id, kind, limit + 1, lifecycle, after, archived)
    has_more = len(rows) > limit
    rows = rows[:limit]
    return PlanningListResponse(
        items=cast(
            list[PlanningItemResponse],
            [_typed_response(row, response_type) for row in rows],
        ),
        next_cursor=_encode_cursor(owner_id, kind, lifecycle, rows[-1], archived)
        if has_more and rows
        else None,
    )


def _create[T: BaseModel](
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    kind: PlanningKind,
    payload: object,
    notes: str | None,
    response_type: type[T],
    response: Response,
    ai_use_allowed: bool = False,
    cross_domain_use_allowed: bool = False,
) -> T:
    aggregate, created = create_planning_resource(
        session,
        owner_id,
        object_id,
        kind,
        payload,
        notes,
        ai_use_allowed,
        cross_domain_use_allowed,
    )
    response.status_code = 201 if created else 200
    return _typed_response(aggregate, response_type)


def _history(
    session: Session, owner_id: UUID, object_id: UUID, kind: str, after_revision: int, limit: int
) -> PlanningHistoryResponse:
    rows = list_planning_history(session, owner_id, object_id, kind, after_revision, limit + 1)
    has_more = len(rows) > limit
    rows = rows[:limit]
    return PlanningHistoryResponse(
        items=[
            PlanningHistoryEntry(
                revision=row.revision,
                recorded_at=row.recorded_at,
                actor_kind="user",
                reason=cast(Literal["create", "update", "archive"], row.reason),
                snapshot=row.snapshot,
            )
            for row in rows
        ],
        next_after_revision=rows[-1].revision if has_more and rows else None,
    )


def _lifecycle[T: BaseModel](
    session: Session,
    owner_id: UUID,
    object_id: UUID,
    kind: PlanningKind,
    body: LifecycleUpdateRequest,
    response_type: type[T],
) -> T:
    aggregate = transition_planning_resource(
        session, owner_id, object_id, kind, body.expected_revision, body.lifecycle.value
    )
    return _typed_response(aggregate, response_type)


@router.get(
    "/goals", response_model=PlanningListResponse, operation_id="listGoals", responses=COMMON_ERRORS
)
def list_goals(
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    lifecycle: GoalLifecycle | None = None,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
    archived: bool = False,
) -> PlanningListResponse:
    return _list(
        session,
        owner,
        "goal",
        limit,
        None if archived else lifecycle.value if lifecycle else None,
        cursor,
        GoalResponse,
        archived,
    )


@router.post(
    "/goals",
    response_model=GoalResponse,
    status_code=201,
    operation_id="createGoal",
    responses=COMMON_ERRORS,
)
def create_goal(
    body: GoalCreateRequest,
    response: Response,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> GoalResponse:
    return _create(
        session,
        owner,
        body.id,
        "goal",
        body.goal,
        body.notes,
        GoalResponse,
        response,
        body.ai_use_allowed,
        body.cross_domain_use_allowed,
    )


@router.get(
    "/goals/{goal_id}", response_model=GoalResponse, operation_id="getGoal", responses=COMMON_ERRORS
)
def get_goal(
    goal_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> GoalResponse:
    return _typed_response(get_planning_resource(session, owner, goal_id, "goal"), GoalResponse)


@router.patch(
    "/goals/{goal_id}",
    response_model=GoalResponse,
    operation_id="updateGoal",
    responses=COMMON_ERRORS,
)
def update_goal(
    goal_id: UUID,
    body: GoalUpdateRequest,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> GoalResponse:
    return _typed_response(
        update_planning_resource(
            session,
            owner,
            goal_id,
            "goal",
            body.expected_revision,
            body.goal,
            body.ai_use_allowed,
            body.cross_domain_use_allowed,
        ),
        GoalResponse,
    )


@router.patch(
    "/goals/{goal_id}/lifecycle",
    response_model=GoalResponse,
    operation_id="transitionGoal",
    responses=COMMON_ERRORS,
)
def transition_goal(
    goal_id: UUID,
    body: LifecycleUpdateRequest,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> GoalResponse:
    return _lifecycle(session, owner, goal_id, "goal", body, GoalResponse)


@router.delete(
    "/goals/{goal_id}",
    response_model=GoalResponse,
    operation_id="archiveGoal",
    responses=COMMON_ERRORS,
)
def archive_goal(
    goal_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    expected_revision: Annotated[int, Query(ge=1)],
) -> GoalResponse:
    return _typed_response(
        archive_planning_resource(session, owner, goal_id, "goal", expected_revision), GoalResponse
    )


@router.get(
    "/goals/{goal_id}/history",
    response_model=PlanningHistoryResponse,
    operation_id="listGoalHistory",
    responses=COMMON_ERRORS,
)
def goal_history(
    goal_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PlanningHistoryResponse:
    return _history(session, owner, goal_id, "goal", after_revision, limit)


@router.get(
    "/regimens",
    response_model=PlanningListResponse,
    operation_id="listRegimens",
    responses=COMMON_ERRORS,
)
def list_regimens(
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    lifecycle: RegimenLifecycle | None = None,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
    archived: bool = False,
) -> PlanningListResponse:
    return _list(
        session,
        owner,
        "regimen",
        limit,
        None if archived else lifecycle.value if lifecycle else None,
        cursor,
        RegimenResponse,
        archived,
    )


@router.post(
    "/regimens",
    response_model=RegimenResponse,
    status_code=201,
    operation_id="createRegimen",
    responses=COMMON_ERRORS,
)
def create_regimen(
    body: RegimenCreateRequest,
    response: Response,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> RegimenResponse:
    return _create(
        session,
        owner,
        body.id,
        "regimen",
        body.regimen,
        body.notes,
        RegimenResponse,
        response,
        body.ai_use_allowed,
        body.cross_domain_use_allowed,
    )


@router.get(
    "/regimens/{regimen_id}",
    response_model=RegimenResponse,
    operation_id="getRegimen",
    responses=COMMON_ERRORS,
)
def get_regimen(
    regimen_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> RegimenResponse:
    return _typed_response(
        get_planning_resource(session, owner, regimen_id, "regimen"), RegimenResponse
    )


@router.patch(
    "/regimens/{regimen_id}",
    response_model=RegimenResponse,
    operation_id="updateRegimen",
    responses=COMMON_ERRORS,
)
def update_regimen(
    regimen_id: UUID,
    body: RegimenUpdateRequest,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> RegimenResponse:
    return _typed_response(
        update_planning_resource(
            session,
            owner,
            regimen_id,
            "regimen",
            body.expected_revision,
            body.regimen,
            body.ai_use_allowed,
            body.cross_domain_use_allowed,
        ),
        RegimenResponse,
    )


@router.patch(
    "/regimens/{regimen_id}/lifecycle",
    response_model=RegimenResponse,
    operation_id="transitionRegimen",
    responses=COMMON_ERRORS,
)
def transition_regimen(
    regimen_id: UUID,
    body: LifecycleUpdateRequest,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> RegimenResponse:
    return _lifecycle(session, owner, regimen_id, "regimen", body, RegimenResponse)


@router.delete(
    "/regimens/{regimen_id}",
    response_model=RegimenResponse,
    operation_id="archiveRegimen",
    responses=COMMON_ERRORS,
)
def archive_regimen(
    regimen_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    expected_revision: Annotated[int, Query(ge=1)],
) -> RegimenResponse:
    return _typed_response(
        archive_planning_resource(session, owner, regimen_id, "regimen", expected_revision),
        RegimenResponse,
    )


@router.get(
    "/regimens/{regimen_id}/history",
    response_model=PlanningHistoryResponse,
    operation_id="listRegimenHistory",
    responses=COMMON_ERRORS,
)
def regimen_history(
    regimen_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PlanningHistoryResponse:
    return _history(session, owner, regimen_id, "regimen", after_revision, limit)


@router.get(
    "/plans", response_model=PlanningListResponse, operation_id="listPlans", responses=COMMON_ERRORS
)
def list_plans(
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    lifecycle: PlanLifecycle | None = None,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
    archived: bool = False,
) -> PlanningListResponse:
    return _list(
        session,
        owner,
        "plan",
        limit,
        None if archived else lifecycle.value if lifecycle else None,
        cursor,
        PlanResponse,
        archived,
    )


@router.post(
    "/plans",
    response_model=PlanResponse,
    status_code=201,
    operation_id="createPlan",
    responses=COMMON_ERRORS,
)
def create_plan(
    body: PlanCreateRequest,
    response: Response,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> PlanResponse:
    return _create(
        session,
        owner,
        body.id,
        "plan",
        body.plan,
        body.notes,
        PlanResponse,
        response,
        body.ai_use_allowed,
        body.cross_domain_use_allowed,
    )


@router.get(
    "/plans/{plan_id}", response_model=PlanResponse, operation_id="getPlan", responses=COMMON_ERRORS
)
def get_plan(
    plan_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> PlanResponse:
    return _typed_response(get_planning_resource(session, owner, plan_id, "plan"), PlanResponse)


@router.patch(
    "/plans/{plan_id}",
    response_model=PlanResponse,
    operation_id="updatePlan",
    responses=COMMON_ERRORS,
)
def update_plan(
    plan_id: UUID,
    body: PlanUpdateRequest,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> PlanResponse:
    return _typed_response(
        update_planning_resource(
            session,
            owner,
            plan_id,
            "plan",
            body.expected_revision,
            body.plan,
            body.ai_use_allowed,
            body.cross_domain_use_allowed,
        ),
        PlanResponse,
    )


@router.put(
    "/plans/{plan_id}/items/order",
    response_model=PlanResponse,
    operation_id="reorderPlanItems",
    responses=COMMON_ERRORS,
)
def reorder_plan(
    plan_id: UUID,
    body: PlanOrderRequest,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> PlanResponse:
    return _typed_response(
        reorder_plan_items(session, owner, plan_id, body.expected_revision, body.item_ids),
        PlanResponse,
    )


@router.patch(
    "/plans/{plan_id}/lifecycle",
    response_model=PlanResponse,
    operation_id="transitionPlan",
    responses=COMMON_ERRORS,
)
def transition_plan(
    plan_id: UUID,
    body: LifecycleUpdateRequest,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> PlanResponse:
    return _lifecycle(session, owner, plan_id, "plan", body, PlanResponse)


@router.delete(
    "/plans/{plan_id}",
    response_model=PlanResponse,
    operation_id="archivePlan",
    responses=COMMON_ERRORS,
)
def archive_plan(
    plan_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    expected_revision: Annotated[int, Query(ge=1)],
) -> PlanResponse:
    return _typed_response(
        archive_planning_resource(session, owner, plan_id, "plan", expected_revision), PlanResponse
    )


@router.get(
    "/plans/{plan_id}/history",
    response_model=PlanningHistoryResponse,
    operation_id="listPlanHistory",
    responses=COMMON_ERRORS,
)
def plan_history(
    plan_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PlanningHistoryResponse:
    return _history(session, owner, plan_id, "plan", after_revision, limit)


@router.get(
    "/contexts",
    response_model=PlanningListResponse,
    operation_id="listContexts",
    responses=COMMON_ERRORS,
)
def list_contexts(
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    lifecycle: ContextLifecycle | None = None,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
    archived: bool = False,
) -> PlanningListResponse:
    return _list(
        session,
        owner,
        "context",
        limit,
        None if archived else lifecycle.value if lifecycle else None,
        cursor,
        ContextResponse,
        archived,
    )


@router.post(
    "/contexts",
    response_model=ContextResponse,
    status_code=201,
    operation_id="createContext",
    responses=COMMON_ERRORS,
)
def create_context(
    body: ContextCreateRequest,
    response: Response,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ContextResponse:
    return _create(
        session,
        owner,
        body.id,
        "context",
        body.context,
        body.notes,
        ContextResponse,
        response,
        body.ai_use_allowed,
        body.cross_domain_use_allowed,
    )


@router.get(
    "/contexts/{context_id}",
    response_model=ContextResponse,
    operation_id="getContext",
    responses=COMMON_ERRORS,
)
def get_context(
    context_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ContextResponse:
    return _typed_response(
        get_planning_resource(session, owner, context_id, "context"), ContextResponse
    )


@router.patch(
    "/contexts/{context_id}",
    response_model=ContextResponse,
    operation_id="updateContext",
    responses=COMMON_ERRORS,
)
def update_context(
    context_id: UUID,
    body: ContextUpdateRequest,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ContextResponse:
    return _typed_response(
        update_planning_resource(
            session,
            owner,
            context_id,
            "context",
            body.expected_revision,
            body.context,
            body.ai_use_allowed,
            body.cross_domain_use_allowed,
        ),
        ContextResponse,
    )


@router.patch(
    "/contexts/{context_id}/lifecycle",
    response_model=ContextResponse,
    operation_id="transitionContext",
    responses=COMMON_ERRORS,
)
def transition_context(
    context_id: UUID,
    body: LifecycleUpdateRequest,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ContextResponse:
    return _lifecycle(session, owner, context_id, "context", body, ContextResponse)


@router.delete(
    "/contexts/{context_id}",
    response_model=ContextResponse,
    operation_id="archiveContext",
    responses=COMMON_ERRORS,
)
def archive_context(
    context_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    expected_revision: Annotated[int, Query(ge=1)],
) -> ContextResponse:
    return _typed_response(
        archive_planning_resource(session, owner, context_id, "context", expected_revision),
        ContextResponse,
    )


@router.get(
    "/contexts/{context_id}/history",
    response_model=PlanningHistoryResponse,
    operation_id="listContextHistory",
    responses=COMMON_ERRORS,
)
def context_history(
    context_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PlanningHistoryResponse:
    return _history(session, owner, context_id, "context", after_revision, limit)


@router.get(
    "/trackers",
    response_model=PlanningListResponse,
    operation_id="listTrackers",
    responses=COMMON_ERRORS,
)
def list_trackers(
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
    archived: bool = False,
) -> PlanningListResponse:
    return _list(
        session,
        owner,
        "tracker_definition",
        limit,
        None if archived else "active",
        cursor,
        TrackerResponse,
        archived,
    )


@router.post(
    "/trackers",
    response_model=TrackerResponse,
    status_code=201,
    operation_id="createTracker",
    responses=COMMON_ERRORS,
)
def create_tracker(
    body: TrackerCreateRequest,
    response: Response,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> TrackerResponse:
    return _create(
        session,
        owner,
        body.id,
        "tracker_definition",
        body.definition,
        body.notes,
        TrackerResponse,
        response,
        body.ai_use_allowed,
        body.cross_domain_use_allowed,
    )


@router.get(
    "/trackers/{tracker_id}",
    response_model=TrackerResponse,
    operation_id="getTracker",
    responses=COMMON_ERRORS,
)
def get_tracker(
    tracker_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> TrackerResponse:
    return _typed_response(
        get_planning_resource(session, owner, tracker_id, "tracker_definition"), TrackerResponse
    )


@router.patch(
    "/trackers/{tracker_id}",
    response_model=TrackerResponse,
    operation_id="updateTracker",
    responses=COMMON_ERRORS,
)
def update_tracker(
    tracker_id: UUID,
    body: TrackerUpdateRequest,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> TrackerResponse:
    return _typed_response(
        update_planning_resource(
            session,
            owner,
            tracker_id,
            "tracker_definition",
            body.expected_revision,
            body.definition,
            body.ai_use_allowed,
            body.cross_domain_use_allowed,
        ),
        TrackerResponse,
    )


@router.delete(
    "/trackers/{tracker_id}",
    response_model=TrackerResponse,
    operation_id="archiveTracker",
    responses=COMMON_ERRORS,
)
def archive_tracker(
    tracker_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    expected_revision: Annotated[int, Query(ge=1)],
) -> TrackerResponse:
    return _typed_response(
        archive_planning_resource(
            session, owner, tracker_id, "tracker_definition", expected_revision
        ),
        TrackerResponse,
    )


@router.get(
    "/trackers/{tracker_id}/history",
    response_model=PlanningHistoryResponse,
    operation_id="listTrackerHistory",
    responses=COMMON_ERRORS,
)
def tracker_history(
    tracker_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PlanningHistoryResponse:
    return _history(session, owner, tracker_id, "tracker_definition", after_revision, limit)


@router.get(
    "/trackers/{tracker_id}/versions",
    response_model=TrackerSchemaVersionListResponse,
    operation_id="listTrackerVersions",
    responses=COMMON_ERRORS,
)
def tracker_versions(
    tracker_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    after_version: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TrackerSchemaVersionListResponse:
    get_planning_resource(session, owner, tracker_id, "tracker_definition")
    rows = list(
        session.scalars(
            select(TrackerSchemaVersion)
            .where(
                TrackerSchemaVersion.owner_id == owner,
                TrackerSchemaVersion.tracker_id == tracker_id,
                TrackerSchemaVersion.version > after_version,
            )
            .order_by(TrackerSchemaVersion.version.asc())
            .limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return TrackerSchemaVersionListResponse(
        items=[
            TrackerSchemaVersionResponse(
                version=row.version,
                definition=TrackerDefinitionV1.model_validate(row.definition),
                created_at=row.created_at,
            )
            for row in rows
        ],
        next_after_version=rows[-1].version if has_more and rows else None,
    )


@router.put(
    "/regimens/{regimen_id}/schedule",
    response_model=ScheduleResponse,
    operation_id="editRegimenSchedule",
    responses=COMMON_ERRORS,
)
def edit_regimen_schedule(
    regimen_id: UUID,
    body: ScheduleEditRequest,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ScheduleResponse:
    value = set_planning_schedule(
        session,
        owner,
        regimen_id,
        "regimen",
        None,
        body.expected_schedule_revision,
        body.effective_from,
        body.schedule,
    )
    return ScheduleResponse.model_validate(value)


@router.get(
    "/regimens/{regimen_id}/schedule",
    response_model=ScheduleResponse | None,
    operation_id="getRegimenSchedule",
    responses=COMMON_ERRORS,
)
def regimen_schedule(
    regimen_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ScheduleResponse | None:
    value = get_planning_schedule(session, owner, regimen_id, "regimen", None)
    return ScheduleResponse.model_validate(value) if value is not None else None


@router.put(
    "/plans/{plan_id}/items/{item_id}/schedule",
    response_model=ScheduleResponse,
    operation_id="editPlanItemSchedule",
    responses=COMMON_ERRORS,
)
def edit_plan_item_schedule(
    plan_id: UUID,
    item_id: UUID,
    body: ScheduleEditRequest,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ScheduleResponse:
    value = set_planning_schedule(
        session,
        owner,
        plan_id,
        "plan",
        item_id,
        body.expected_schedule_revision,
        body.effective_from,
        body.schedule,
    )
    return ScheduleResponse.model_validate(value)


@router.get(
    "/plans/{plan_id}/items/{item_id}/schedule",
    response_model=ScheduleResponse | None,
    operation_id="getPlanItemSchedule",
    responses=COMMON_ERRORS,
)
def plan_item_schedule(
    plan_id: UUID,
    item_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> ScheduleResponse | None:
    value = get_planning_schedule(session, owner, plan_id, "plan", item_id)
    return ScheduleResponse.model_validate(value) if value is not None else None


@router.get(
    "/regimens/{regimen_id}/occurrences",
    response_model=OccurrenceListResponse,
    operation_id="listRegimenOccurrences",
    responses=COMMON_ERRORS,
)
def regimen_occurrences(
    regimen_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    start_date: date,
    end_date: date,
    timezone: Annotated[str, Query(max_length=64)],
) -> OccurrenceListResponse:
    return OccurrenceListResponse(
        items=[
            OccurrenceResponse.model_validate(item)
            for item in list_planning_occurrences(
                session, owner, regimen_id, "regimen", start_date, end_date, timezone
            )
        ]
    )


@router.get(
    "/plans/{plan_id}/occurrences",
    response_model=OccurrenceListResponse,
    operation_id="listPlanOccurrences",
    responses=COMMON_ERRORS,
)
def plan_occurrences(
    plan_id: UUID,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    start_date: date,
    end_date: date,
    timezone: Annotated[str, Query(max_length=64)],
) -> OccurrenceListResponse:
    return OccurrenceListResponse(
        items=[
            OccurrenceResponse.model_validate(item)
            for item in list_planning_occurrences(
                session, owner, plan_id, "plan", start_date, end_date, timezone
            )
        ]
    )


@router.patch(
    "/plan-occurrences/{occurrence_key}",
    response_model=OccurrenceActionResponse,
    operation_id="updatePlanOccurrence",
    responses=COMMON_ERRORS,
)
def update_occurrence(
    occurrence_key: str,
    body: OccurrenceActionRequest,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
) -> OccurrenceActionResponse:
    return OccurrenceActionResponse.model_validate(
        record_occurrence_action(
            session,
            owner,
            occurrence_key,
            body.expected_schedule_revision,
            body.expected_override_revision,
            body.state,
            body.rescheduled_at,
            body.linked_event_id,
            body.linked_observation_id,
            replace_link=bool({"linked_event_id", "linked_observation_id"} & body.model_fields_set),
        )
    )


@router.get(
    "/plan-occurrences/{occurrence_key}/history",
    response_model=OccurrenceHistoryResponse,
    operation_id="listPlanOccurrenceHistory",
    responses=COMMON_ERRORS,
)
def occurrence_history(
    occurrence_key: str,
    owner: Annotated[UUID, Depends(get_current_owner)],
    session: Annotated[Session, Depends(get_session)],
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> OccurrenceHistoryResponse:
    rows = list_occurrence_history(session, owner, occurrence_key, after_revision, limit + 1)
    has_more = len(rows) > limit
    rows = rows[:limit]
    return OccurrenceHistoryResponse(
        items=[
            OccurrenceHistoryEntry(
                revision=row.revision,
                action=cast(Literal["completed", "skipped", "rescheduled"], row.action),
                schedule_revision=row.schedule_revision,
                acted_at=row.acted_at,
                rescheduled_at=row.rescheduled_at,
                linked_event_id=row.linked_event_id,
                linked_observation_id=row.linked_observation_id,
            )
            for row in rows
        ],
        next_after_revision=rows[-1].revision if has_more and rows else None,
    )
