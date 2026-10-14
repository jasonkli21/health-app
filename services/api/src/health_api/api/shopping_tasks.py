"""Explicit user-controlled source host using the suite task control protocol."""

import asyncio
import time
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from health_api.api.dependencies import get_current_owner, get_session
from health_api.application.shopping_commands import ErgonomicTaskChoice, ShoppingCommandService
from health_api.integrations.task_client import task_client
from health_api.integrations.task_control import (
    SourceTaskConfirmation,
    SourceTaskStatus,
    TaskControlRejected,
    TaskControlUnavailable,
    source_task_status,
    submitted_source_task,
)
from health_api.integrations.task_identity import incoming_owner, source_principal
from health_api.integrations.task_wire import (
    COMMAND_READ_FINGERPRINT,
    DelegatedCommandRead,
    DelegatedSourceCommand,
)

router = APIRouter(prefix="", tags=["Delegated Shopping tasks"])
SessionDependency = Annotated[Session, Depends(get_session)]
OwnerDependency = Annotated[UUID, Depends(get_current_owner)]
PREFIX = "/shopping-tasks"


def _relay(
    request: Request,
    session: Session,
    owner_id: UUID,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    principal = source_principal(request, session, owner_id)
    client = getattr(request.app.state, "task_control_client", None) or task_client(
        request.app.state.settings.task_control
    )
    try:
        return client.request(principal, method, path, body)
    except TaskControlRejected as error:
        raise HTTPException(error.status, "task_control_rejected") from error
    except TaskControlUnavailable as error:
        raise HTTPException(503, "task_control_unavailable") from error


@router.get(PREFIX + "/capabilities", operation_id="getShoppingTaskCapabilities")
def capabilities(request: Request, owner_id: OwnerDependency) -> dict[str, bool]:
    auth_time = getattr(request.state, "auth_time", None)
    return {
        "enabled": request.app.state.settings.task_control is not None,
        "recent_authentication": type(auth_time) is int
        and -30 <= int(time.time()) - auth_time <= 300,
    }


@router.get(PREFIX + "/choices", operation_id="listShoppingTaskChoices")
def choices(
    request: Request, session: SessionDependency, owner_id: OwnerDependency
) -> dict[str, Any]:
    return _relay(request, session, owner_id, "GET", "/v1/federation/grants/choices")


@router.post(
    PREFIX + "/commands",
    response_model=DelegatedSourceCommand,
    status_code=201,
    operation_id="createShoppingSourceCommand",
)
def create(
    request: Request,
    choice: ErgonomicTaskChoice,
    session: SessionDependency,
    owner_id: OwnerDependency,
) -> DelegatedSourceCommand:
    source_principal(request, session, owner_id)
    command = ShoppingCommandService(session, owner_id).create(
        choice, request.app.state.settings.task_control.operation_fingerprint
    )
    session.commit()
    return command


@router.post(
    "/internal/personal-ai/commands/read",
    response_model=DelegatedSourceCommand,
    include_in_schema=False,
)
async def read(request: Request, session: SessionDependency) -> DelegatedSourceCommand:
    if request.app.state.settings.task_control is None:
        raise HTTPException(404, "not_found")
    data = bytearray()
    try:
        async with asyncio.timeout(3):
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 8192:
                    raise HTTPException(413, "task_request_too_large")
        body = DelegatedCommandRead.model_validate_json(data)
        if (
            body.destination_application_id != "health"
            or body.workspace_id is not None
            or request.headers.get("x-task-contract-fingerprint") != COMMAND_READ_FINGERPRINT
        ):
            raise ValueError
    except TimeoutError as error:
        raise HTTPException(408, "task_request_timeout") from error
    except ValueError as error:
        raise HTTPException(409, "task_contract_unsupported") from error
    owner = await run_in_threadpool(incoming_owner, request, session, body.model_dump(mode="json"))
    return ShoppingCommandService(session, owner).current(body.command_id)


@router.post(
    PREFIX + "/commands/{command_id}/submit",
    response_model=SourceTaskStatus,
    operation_id="submitShoppingSourceCommand",
)
def submit(
    request: Request, command_id: UUID, session: SessionDependency, owner_id: OwnerDependency
) -> SourceTaskStatus:
    service = ShoppingCommandService(session, owner_id)
    service.owned(command_id)
    result = _relay(
        request,
        session,
        owner_id,
        "POST",
        "/v1/mutations/commands",
        {"source_application_id": "health", "command_id": str(command_id)},
    )
    try:
        status = submitted_source_task(result, "health", command_id)
    except TaskControlUnavailable as error:
        raise HTTPException(503, "task_control_response_invalid") from error
    service.bind(command_id, status.proposal_id)
    session.commit()
    return status


def _proposal(session: Session, owner_id: UUID, command_id: UUID) -> UUID:
    row = ShoppingCommandService(session, owner_id).owned(command_id)
    if row.proposal_id is None:
        raise HTTPException(409, "command_not_submitted")
    return row.proposal_id


@router.post(
    PREFIX + "/commands/{command_id}/{action}",
    response_model=SourceTaskStatus,
    operation_id="controlShoppingSourceCommand",
)
def control(
    request: Request,
    command_id: UUID,
    action: Literal["validate", "confirm", "apply", "reconcile"],
    session: SessionDependency,
    owner_id: OwnerDependency,
    confirmation: SourceTaskConfirmation | None = None,
) -> SourceTaskStatus:
    if (action in {"confirm", "apply"}) != (confirmation is not None):
        raise HTTPException(422, "task_confirmation_required")
    proposal = _proposal(session, owner_id, command_id)
    try:
        return source_task_status(
            _relay(
                request,
                session,
                owner_id,
                "POST",
                f"/v1/mutations/{proposal}/{action}",
                confirmation.model_dump(mode="json") if confirmation else None,
            ),
            expected_proposal_id=proposal,
        )
    except TaskControlUnavailable as error:
        raise HTTPException(503, "task_control_response_invalid") from error


@router.get(
    PREFIX + "/commands/{command_id}",
    response_model=SourceTaskStatus,
    operation_id="getShoppingSourceCommandStatus",
)
def status(
    request: Request, command_id: UUID, session: SessionDependency, owner_id: OwnerDependency
) -> SourceTaskStatus:
    proposal = _proposal(session, owner_id, command_id)
    try:
        return source_task_status(
            _relay(request, session, owner_id, "GET", f"/v1/mutations/{proposal}"),
            expected_proposal_id=proposal,
        )
    except TaskControlUnavailable as error:
        raise HTTPException(503, "task_control_response_invalid") from error
