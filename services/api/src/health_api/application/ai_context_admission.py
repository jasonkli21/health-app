"""Owner, consent, lifecycle, time, domain, and type admission for context/search candidates."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from health_api.application.ai_context_ranking import (
    _common_vector,
    _payload_vector,
    _relevance_expression,
    _search_match_expression,
)
from health_api.domain.ai import (
    AIResourceType,
)
from health_api.domain.daily import local_day_bounds
from health_api.persistence.models import (
    EventItem,
    HealthObject,
    ObservationItem,
    PlanningResource,
    ProfileItem,
    Source,
)
from sqlalchemy import (
    Date,
    DateTime,
    Integer,
    String,
    and_,
    case,
    cast,
    func,
    literal,
    literal_column,
    or_,
    select,
    union_all,
)


def _eligibility_conditions(
    owner_id: UUID,
    *,
    object_type: AIResourceType,
    payload: Any,
    as_of: datetime,
    start_date: date,
    start_at: datetime,
    end_date: date,
    excluded_object_ids: tuple[UUID, ...] = (),
    domains: tuple[str, ...] = (),
) -> list[Any]:
    """The single SQL admission gate shared by preview and search candidates."""
    conditions: list[Any] = [
        HealthObject.owner_id == owner_id,
        HealthObject.object_type == object_type,
        HealthObject.status == "active",
        HealthObject.ai_use_allowed.is_(True),
        and_(
            or_(HealthObject.valid_from.is_(None), HealthObject.valid_from <= as_of),
            or_(HealthObject.valid_to.is_(None), HealthObject.valid_to > as_of),
        ),
    ]
    if domains:
        conditions.append(HealthObject.domain.in_(domains))
    if excluded_object_ids:
        conditions.append(HealthObject.id.not_in(excluded_object_ids))
    if object_type in {"event", "observation"}:
        if object_type == "event":
            instant_time = EventItem.occurred_at
            interval_end = EventItem.ended_at
            precision = EventItem.time_precision
            local_date = EventItem.local_date
        else:
            instant_time = ObservationItem.observed_at
            interval_end = ObservationItem.interval_end
            precision = ObservationItem.time_precision
            local_date = ObservationItem.local_date
        conditions.append(
            or_(
                and_(
                    precision == "instant",
                    instant_time < as_of,
                    or_(
                        and_(interval_end.is_(None), instant_time >= start_at),
                        interval_end > start_at,
                    ),
                ),
                and_(precision == "date_only", local_date >= start_date, local_date <= end_date),
            )
        )
    if object_type in {"goal", "regimen", "plan", "context"}:
        conditions.append(PlanningResource.lifecycle == "active")
        # Payload dates are canonical planning validity. Context intervals are
        # half-open; plan and regimen endings are inclusive. Goal targets are
        # deadlines, so only their start date limits current eligibility.
        if object_type == "context":
            conditions.extend(
                (
                    or_(
                        payload["start_at"].astext.is_(None),
                        payload["start_at"].astext <= end_date.isoformat(),
                    ),
                    or_(
                        payload["end_at"].astext.is_(None),
                        payload["end_at"].astext > end_date.isoformat(),
                    ),
                )
            )
        else:
            conditions.append(
                or_(
                    payload["start_date"].astext.is_(None),
                    payload["start_date"].astext <= end_date.isoformat(),
                )
            )
            if object_type in {"regimen", "plan"}:
                conditions.append(
                    or_(
                        payload["end_date"].astext.is_(None),
                        payload["end_date"].astext >= end_date.isoformat(),
                    )
                )
    if object_type == "observation":
        # Custom tracker values stay excluded until their immutable schema can
        # be joined into the authorized context.
        conditions.append(ObservationItem.payload["value"]["metric"].astext != "custom")
    return conditions


def _candidate_branch(
    owner_id: UUID,
    *,
    object_type: AIResourceType,
    payload: Any,
    task_query: Any,
    as_of: datetime,
    start_date: date,
    start_at: datetime,
    end_date: date,
    search_query: Any | None,
    excluded_object_ids: tuple[UUID, ...] = (),
    domains: tuple[str, ...] = (),
) -> Any:
    common_vector = _common_vector()
    payload_vector = _payload_vector(payload)
    relevance = _relevance_expression(common_vector, payload_vector, task_query)
    conditions = _eligibility_conditions(
        owner_id,
        object_type=object_type,
        payload=payload,
        as_of=as_of,
        start_date=start_date,
        start_at=start_at,
        end_date=end_date,
        excluded_object_ids=excluded_object_ids,
        domains=domains,
    )
    if search_query is not None:
        conditions.append(_search_match_expression(common_vector, payload_vector, search_query))

    join_model: Any
    extra_values: tuple[Any, ...]
    priority: Any
    context_priority: Any
    if object_type == "profile_item":
        join_model = ProfileItem
        extra_values = (
            literal(None, type_=String()).label("time_precision"),
            literal(None, type_=DateTime(timezone=True)).label("occurred_at"),
            literal(None, type_=Date()).label("local_date"),
            literal(None, type_=DateTime(timezone=True)).label("ended_at"),
            literal(None, type_=String()).label("timezone"),
        )
        profile_kind = ProfileItem.kind
        priority = case(
            (profile_kind == "constraint", 0),
            (profile_kind == "preference", 2),
            else_=3,
        )
        context_priority = literal(0, type_=Integer())
    elif object_type == "event":
        join_model = EventItem
        extra_values = (
            EventItem.time_precision.label("time_precision"),
            EventItem.occurred_at.label("occurred_at"),
            EventItem.local_date.label("local_date"),
            EventItem.ended_at.label("ended_at"),
            EventItem.timezone.label("timezone"),
        )
        priority = literal(4, type_=Integer())
        context_priority = literal(0, type_=Integer())
    elif object_type == "observation":
        join_model = ObservationItem
        extra_values = (
            ObservationItem.time_precision.label("time_precision"),
            ObservationItem.observed_at.label("occurred_at"),
            ObservationItem.local_date.label("local_date"),
            ObservationItem.interval_end.label("ended_at"),
            ObservationItem.timezone.label("timezone"),
        )
        priority = literal(4, type_=Integer())
        context_priority = literal(0, type_=Integer())
    else:
        join_model = PlanningResource
        extra_values = (
            literal(None, type_=String()).label("time_precision"),
            literal(None, type_=DateTime(timezone=True)).label("occurred_at"),
            literal(None, type_=Date()).label("local_date"),
            literal(None, type_=DateTime(timezone=True)).label("ended_at"),
            literal(None, type_=String()).label("timezone"),
        )
        priority = literal(1 if object_type == "context" else 2, type_=Integer())
        context_priority = (
            cast(PlanningResource.payload["priority"].astext, Integer)
            if object_type == "context"
            else literal(0, type_=Integer())
        )

    join_condition = and_(
        join_model.owner_id == HealthObject.owner_id,
        join_model.object_id == HealthObject.id,
    )
    return (
        select(
            HealthObject.id.label("object_id"),
            literal(object_type, type_=String()).label("object_type"),
            HealthObject.domain.label("domain"),
            HealthObject.title.label("title"),
            HealthObject.valid_from.label("valid_from"),
            HealthObject.valid_to.label("valid_to"),
            HealthObject.recorded_at.label("recorded_at"),
            Source.source_kind.label("source_kind"),
            HealthObject.confirmation_status.label("confirmation_status"),
            HealthObject.revision.label("revision"),
            HealthObject.metadata_json.label("health_metadata"),
            HealthObject.notes.label("notes"),
            payload.label("payload"),
            *extra_values,
            priority.label("priority"),
            context_priority.label("context_priority"),
            case((HealthObject.confirmation_status == "user_confirmed", 0), else_=1).label(
                "confirmation_priority"
            ),
            relevance.label("relevance"),
        )
        .select_from(HealthObject)
        .join(join_model, join_condition)
        .join(
            Source,
            and_(Source.owner_id == HealthObject.owner_id, Source.id == HealthObject.source_id),
        )
        .where(*conditions)
    )


def _eligible_candidates(
    owner_id: UUID,
    *,
    resource_types: tuple[AIResourceType, ...],
    task: str,
    as_of: datetime,
    timezone: str,
    lookback_days: int,
    excluded_object_ids: tuple[UUID, ...] = (),
    search_text: str | None = None,
    domains: tuple[str, ...] = (),
) -> Any:
    try:
        local_date = as_of.astimezone(ZoneInfo(timezone)).date()
    except (OverflowError, ValueError) as exc:
        raise ValueError("Context date is outside the supported calendar.") from exc
    try:
        start_date = local_date - timedelta(days=lookback_days)
    except OverflowError as exc:
        raise ValueError("Context date range is outside the supported calendar.") from exc
    if local_date == date.max:
        raise ValueError("Context date range is outside the supported calendar.")
    try:
        start_at = local_day_bounds(start_date, timezone)[0]
    except (OverflowError, ValueError) as exc:
        raise ValueError("Context date range is outside the supported calendar.") from exc
    task_query = func.plainto_tsquery(literal_column("'simple'"), task)
    search_query = (
        func.plainto_tsquery(literal_column("'simple'"), search_text)
        if search_text is not None
        else None
    )
    branches: list[Any] = []
    for object_type in resource_types:
        if object_type == "profile_item":
            payload = ProfileItem.payload
        elif object_type == "event":
            payload = EventItem.payload
        elif object_type == "observation":
            payload = ObservationItem.payload
        else:
            payload = PlanningResource.payload
        branch = _candidate_branch(
            owner_id,
            object_type=object_type,
            payload=payload,
            task_query=task_query,
            as_of=as_of,
            start_date=start_date,
            start_at=start_at,
            end_date=local_date,
            search_query=search_query,
            excluded_object_ids=excluded_object_ids,
            domains=domains,
        )
        branches.append(branch)
    if not branches:
        raise ValueError("at least one resource type is required")
    return union_all(*branches).subquery("eligible_ai_resources")
