"""Build minimized, owner-scoped context and full-text AI search results."""

from __future__ import annotations

import re
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Date,
    DateTime,
    Integer,
    String,
    Text,
    and_,
    case,
    cast,
    func,
    literal,
    literal_column,
    or_,
    select,
    text,
    union_all,
)
from sqlalchemy.orm import Session

from health_api.application.today_service import owner_today_settings
from health_api.domain.ai import (
    AIContextEntry,
    AIContextPack,
    AIContextRequest,
    AIResourceType,
    AISearchResult,
)
from health_api.domain.daily import local_day_bounds
from health_api.domain.daily_rollups import summarize_today
from health_api.domain.schemas import (
    EventSchemaV1,
    ObservationSchemaV1,
    validate_iana_timezone,
)
from health_api.persistence.models import (
    EventItem,
    EventObservationLink,
    HealthObject,
    ObservationItem,
    PlanningResource,
    ProfileItem,
    Source,
)

MAX_CONTEXT_CANDIDATES = 1000
MAX_CONTEXT_ENTRIES = 100
MAX_CONTEXT_BYTES = 65_536
SEARCH_MAX_LOOKBACK_DAYS = 90


def _common_vector():
    return func.to_tsvector(
        literal_column("'simple'"),
        func.coalesce(HealthObject.title, literal_column("''"))
        .op("||")(literal_column("' '"))
        .op("||")(func.coalesce(HealthObject.notes, literal_column("''"))),
    )


def _payload_vector(payload: Any):
    return func.to_tsvector(
        literal_column("'simple'"), cast(_payload_search_projection(payload), Text)
    )


def _payload_search_projection(payload: Any):
    # Relationship labels and identifiers are not search evidence. They are
    # omitted from matching/ranking, as well as from displayed excerpts.
    return payload.op("-")("related").op("-")("items").op("-")("linked_observation_ids")


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
) -> Any:
    common_vector = _common_vector()
    payload_vector = _payload_vector(payload)
    relevance = func.greatest(
        func.ts_rank_cd(common_vector, task_query),
        func.ts_rank_cd(payload_vector, task_query),
    )
    valid_at_as_of = and_(
        or_(HealthObject.valid_from.is_(None), HealthObject.valid_from <= as_of),
        or_(HealthObject.valid_to.is_(None), HealthObject.valid_to > as_of),
    )
    conditions: list[Any] = [
        HealthObject.owner_id == owner_id,
        HealthObject.object_type == object_type,
        HealthObject.status == "active",
        HealthObject.ai_use_allowed.is_(True),
        valid_at_as_of,
    ]
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
        # Payload dates are the canonical planning validity. Context intervals
        # are half-open; plan and regimen endings are inclusive. Goal targets
        # are deadlines, so only their start date limits current eligibility.
        local_selected_date = end_date
        if object_type == "context":
            conditions.extend(
                (
                    or_(
                        payload["start_at"].astext.is_(None),
                        payload["start_at"].astext <= local_selected_date.isoformat(),
                    ),
                    or_(
                        payload["end_at"].astext.is_(None),
                        payload["end_at"].astext > local_selected_date.isoformat(),
                    ),
                )
            )
        elif object_type in {"goal", "regimen", "plan"}:
            conditions.append(
                or_(
                    payload["start_date"].astext.is_(None),
                    payload["start_date"].astext <= local_selected_date.isoformat(),
                )
            )
            if object_type in {"regimen", "plan"}:
                conditions.append(
                    or_(
                        payload["end_date"].astext.is_(None),
                        payload["end_date"].astext >= local_selected_date.isoformat(),
                    )
                )
    if object_type == "observation":
        # Custom tracker values are excluded until their immutable schema
        # labels and units can be joined into the authorized context.
        conditions.append(ObservationItem.payload["value"]["metric"].astext != "custom")
    if search_query is not None:
        conditions.append(
            or_(common_vector.op("@@")(search_query), payload_vector.op("@@")(search_query))
        )

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
        )
        if domains:
            branch = branch.where(HealthObject.domain.in_(domains))
        if excluded_object_ids:
            branch = branch.where(HealthObject.id.not_in(excluded_object_ids))
        branches.append(branch)
    if not branches:
        raise ValueError("at least one resource type is required")
    return union_all(*branches).subquery("eligible_ai_resources")


def _context_entry(row: Any) -> AIContextEntry:
    object_type = row.object_type
    if row.priority == 0:
        relevance_reason = "Current Profile safety constraint"
    elif object_type == "context":
        relevance_reason = "Active context"
    elif object_type in {"goal", "regimen", "plan"}:
        relevance_reason = "Active planning item"
    elif object_type == "profile_item":
        relevance_reason = "Current Profile item"
    else:
        relevance_reason = "Recent health entry"

    content: dict[str, Any] = {"payload": row.payload, "notes": row.notes}
    if row.time_precision is not None:
        time_data: dict[str, Any] = {
            "precision": row.time_precision,
            "timezone": row.timezone,
        }
        if row.time_precision == "instant":
            time_data["occurred_at"] = row.occurred_at.isoformat()
            time_data["ended_at"] = row.ended_at.isoformat() if row.ended_at else None
        else:
            time_data["local_date"] = row.local_date.isoformat()
        content["time"] = time_data
    return AIContextEntry(
        object_id=row.object_id,
        revision=row.revision,
        object_type=object_type,
        domain=row.domain,
        title=row.title,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        source_kind=row.source_kind,
        confirmation_status=row.confirmation_status,
        content=content,
        content_is_user_data=True,
        relevance_reason=relevance_reason,
    )


def _filter_relationships_to_included_entries(entries: list[AIContextEntry]) -> None:
    included_ids = {str(entry.object_id) for entry in entries}
    for entry in entries:
        payload = entry.content.get("payload")
        if not isinstance(payload, dict):
            continue
        if entry.object_type == "context":
            related = payload.get("related")
            if isinstance(related, list):
                payload["related"] = [
                    relation
                    for relation in related
                    if isinstance(relation, dict) and str(relation.get("object_id")) in included_ids
                ]
        elif entry.object_type == "plan":
            items = payload.get("items")
            if isinstance(items, list):
                payload["items"] = [
                    item
                    for item in items
                    if isinstance(item, dict)
                    and (
                        item.get("reference_id") is None
                        or str(item.get("reference_id")) in included_ids
                    )
                ]


def _serialized_size(pack: AIContextPack) -> int:
    return len(pack.model_dump_json().encode("utf-8"))


def _set_serialized_size(pack: AIContextPack) -> int:
    size = 0
    for _ in range(3):
        size = _serialized_size(pack)
        if pack.serialized_bytes == size:
            break
        pack.serialized_bytes = size
    return _serialized_size(pack)


def _today_summaries(
    session: Session,
    owner_id: UUID,
    entries: list[AIContextEntry],
    local_date: date,
    timezone: str,
):
    events: list[tuple[UUID, EventSchemaV1]] = []
    observations: list[tuple[UUID, ObservationSchemaV1]] = []
    included_ids = {entry.object_id for entry in entries}
    linked_observation_ids: set[UUID] = set()
    event_ids = [
        entry.object_id
        for entry in entries
        if entry.object_type == "event" and entry.domain == "symptoms"
    ]
    if event_ids:
        linked_observation_ids = set(
            session.scalars(
                select(EventObservationLink.observation_object_id).where(
                    EventObservationLink.owner_id == owner_id,
                    EventObservationLink.event_object_id.in_(event_ids),
                    EventObservationLink.observation_object_id.in_(included_ids),
                )
            ).all()
        )
    for entry in entries:
        time_data = entry.content.get("time")
        if not isinstance(time_data, dict):
            continue
        clean_time = {key: value for key, value in time_data.items() if key != "ended_at"}
        body = {
            "domain": entry.domain,
            "time": clean_time,
            "payload": entry.content.get("payload"),
            "notes": entry.content.get("notes"),
        }
        if entry.object_type == "event":
            ended_at = time_data.get("ended_at")
            body["ended_at"] = ended_at
            events.append((entry.object_id, EventSchemaV1.model_validate(body)))
        elif entry.object_type == "observation":
            payload = entry.content.get("payload")
            value = payload.get("value", {}) if isinstance(payload, dict) else {}
            if (
                value.get("metric") == "symptom_severity"
                and entry.object_id not in linked_observation_ids
            ):
                continue
            body["interval_end"] = time_data.get("ended_at")
            observations.append((entry.object_id, ObservationSchemaV1.model_validate(body)))
    return summarize_today(events, observations, local_date, timezone)


def build_ai_context(
    session: Session,
    owner_id: UUID,
    request: AIContextRequest,
    *,
    request_id: UUID | None = None,
) -> AIContextPack:
    _, owner_timezone = owner_today_settings(session, owner_id)
    try:
        timezone = validate_iana_timezone(request.timezone or owner_timezone)
    except ValueError as exc:
        raise ValueError("Timezone must be a valid IANA name.") from exc
    try:
        as_of = (request.as_of or datetime.now(UTC)).astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        raise ValueError("Context date is outside the supported calendar.") from exc
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SET LOCAL statement_timeout = '2000ms'"))
    all_eligible = _eligible_candidates(
        owner_id,
        resource_types=tuple(request.resource_types),
        task=request.task,
        as_of=as_of,
        timezone=timezone,
        lookback_days=request.lookback_days,
        domains=tuple(request.domains),
    )
    eligible_total = session.scalar(select(func.count()).select_from(all_eligible)) or 0
    excluded_eligible_count = (
        session.scalar(
            select(func.count())
            .select_from(all_eligible)
            .where(all_eligible.c.object_id.in_(request.excluded_object_ids))
        )
        if request.excluded_object_ids
        else 0
    ) or 0
    candidates = _eligible_candidates(
        owner_id,
        resource_types=tuple(request.resource_types),
        task=request.task,
        as_of=as_of,
        timezone=timezone,
        lookback_days=request.lookback_days,
        excluded_object_ids=tuple(request.excluded_object_ids),
        domains=tuple(request.domains),
    )
    stmt = (
        select(candidates)
        .order_by(
            candidates.c.priority.asc(),
            candidates.c.context_priority.desc(),
            candidates.c.confirmation_priority.asc(),
            candidates.c.relevance.desc(),
            candidates.c.recorded_at.desc(),
            candidates.c.object_id,
        )
        .limit(MAX_CONTEXT_CANDIDATES + 1)
    )
    rows = list(session.execute(stmt).all())
    has_more_candidates = len(rows) > MAX_CONTEXT_CANDIDATES
    rows = rows[:MAX_CONTEXT_CANDIDATES]
    if has_more_candidates and rows[-1].priority == 0:
        raise ValueError("Eligible safety constraints exceed the context preview budget.")

    pack = AIContextPack(
        schema_version=1,
        request_id=request_id or uuid4(),
        owner_scope=secrets.token_hex(16),
        built_at=datetime.now(UTC),
        as_of=as_of,
        timezone=timezone,
        task=request.task,
        task_kind=request.task_kind,
        resource_types=request.resource_types,
        domains=request.domains,
        sections=request.sections,
        lookback_days=request.lookback_days,
        entries=[],
        today_summary_date=as_of.astimezone(ZoneInfo(timezone)).date(),
        today_summary_scope="included_opted_in_entries_only",
        today_summaries=[],
        included_counts={},
        omitted_by_user=excluded_eligible_count,
        omitted_by_budget=0,
        truncated=has_more_candidates,
        budget_bytes=65_536,
        serialized_bytes=0,
    )
    critical_omitted = False
    for row in rows:
        if len(pack.entries) >= MAX_CONTEXT_ENTRIES:
            pack.omitted_by_budget += 1
            pack.truncated = True
            critical_omitted |= row.priority == 0
            continue
        entry = _context_entry(row)
        pack.entries.append(entry)
        current_size = _set_serialized_size(pack)
        if current_size > MAX_CONTEXT_BYTES:
            pack.entries.pop()
            pack.omitted_by_budget += 1
            pack.truncated = True
            critical_omitted |= row.priority == 0
            _set_serialized_size(pack)
    _filter_relationships_to_included_entries(pack.entries)
    _set_serialized_size(pack)
    if critical_omitted:
        raise ValueError("Eligible safety constraints do not fit in the context preview budget.")
    if "today_summaries" in request.sections and {"event", "observation"}.intersection(
        request.resource_types
    ):
        pack.today_summaries = _today_summaries(
            session, owner_id, pack.entries, pack.today_summary_date, timezone
        )
    counts: dict[str, int] = {}
    while True:
        counts.clear()
        for entry in pack.entries:
            counts[entry.object_type] = counts.get(entry.object_type, 0) + 1
        pack.included_counts = counts.copy()
        final_size = _set_serialized_size(pack)
        if final_size <= MAX_CONTEXT_BYTES or not pack.entries:
            break
        removed = pack.entries.pop()
        pack.omitted_by_budget += 1
        pack.truncated = True
        _filter_relationships_to_included_entries(pack.entries)
        payload = removed.content.get("payload")
        if (
            removed.object_type == "profile_item"
            and isinstance(payload, dict)
            and payload.get("kind") == "constraint"
        ):
            critical_omitted = True
        if "today_summaries" in request.sections and {"event", "observation"}.intersection(
            request.resource_types
        ):
            pack.today_summaries = _today_summaries(
                session, owner_id, pack.entries, pack.today_summary_date, timezone
            )
    if critical_omitted:
        raise ValueError("Eligible safety constraints do not fit in the context preview budget.")
    if final_size > MAX_CONTEXT_BYTES:
        raise ValueError("Context preview exceeds the maximum serialized size.")
    pack.omitted_by_budget = max(eligible_total - excluded_eligible_count - len(pack.entries), 0)
    pack.truncated = pack.omitted_by_budget > 0
    _set_serialized_size(pack)
    return pack


def _nested_text(value: Any, key: str | None = None):
    if key in {"related", "reference_id", "object_id", "target_object_id"}:
        return
    if isinstance(value, str):
        if re.fullmatch(r"[0-9a-fA-F-]{36}", value):
            return
        yield value
    elif isinstance(value, dict):
        if value.get("reference_id") is not None:
            return
        for child_key, nested in value.items():
            yield from _nested_text(nested, child_key)
    elif isinstance(value, list):
        for nested in value:
            yield from _nested_text(nested)


def _excerpt(title: str, notes: str | None, payload: Any, query: str) -> str:
    words = [word.casefold() for word in re.findall(r"[\w'-]+", query) if len(word) > 1]
    values = [title, notes or "", *_nested_text(payload)]
    selected = next(
        (value for value in values if any(word in value.casefold() for word in words)),
        title,
    )
    normalized = " ".join(selected.split())
    return normalized[:400]


def search_ai_resources(
    session: Session,
    owner_id: UUID,
    query: str,
    *,
    resource_types: tuple[AIResourceType, ...],
    timezone: str,
    limit: int,
    after: tuple[datetime, UUID] | None = None,
) -> tuple[list[AISearchResult], tuple[datetime, UUID] | None]:
    now = datetime.now(UTC)
    try:
        effective_timezone = validate_iana_timezone(timezone)
    except ValueError as exc:
        raise ValueError("Timezone must be a valid IANA name.") from exc
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SET LOCAL statement_timeout = '2000ms'"))
    candidates = _eligible_candidates(
        owner_id,
        resource_types=resource_types,
        task=query,
        as_of=now,
        timezone=effective_timezone,
        lookback_days=SEARCH_MAX_LOOKBACK_DAYS,
        search_text=query,
    )
    statement = select(candidates)
    if after is not None:
        statement = statement.where(
            or_(
                candidates.c.recorded_at < after[0],
                and_(
                    candidates.c.recorded_at == after[0],
                    candidates.c.object_id > after[1],
                ),
            )
        )
    statement = statement.order_by(
        candidates.c.recorded_at.desc(), candidates.c.object_id.asc()
    ).limit(limit + 1)
    rows = list(session.execute(statement).all())
    page = rows[:limit]
    result = [
        AISearchResult(
            object_id=row.object_id,
            revision=row.revision,
            object_type=row.object_type,
            domain=row.domain,
            title=row.title,
            source_kind=row.source_kind,
            confirmation_status=row.confirmation_status,
            excerpt=_excerpt(row.title, row.notes, _payload_search_projection(row.payload), query),
            time_precision=row.time_precision,
            occurred_at=row.occurred_at,
            local_date=row.local_date,
            interval_end=row.ended_at,
            timezone=row.timezone,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
        )
        for row in page
    ]
    next_after = None
    if len(rows) > limit and page:
        next_after = (page[-1].recorded_at, page[-1].object_id)
    return result, next_after
