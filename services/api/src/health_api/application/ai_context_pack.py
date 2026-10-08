"""Local context pack assembly, Today/trend summaries, and response budgeting."""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from health_api.application.ai_context_admission import _eligible_candidates
from health_api.application.ai_context_contracts import (
    MAX_CONTEXT_BYTES,
    MAX_CONTEXT_CANDIDATES,
    MAX_CONTEXT_ENTRIES,
)
from health_api.application.ai_context_projection import (
    _context_entry,
    _filter_relationships_to_included_entries,
)
from health_api.application.ai_context_ranking import context_candidate_order
from health_api.application.analytics_service import (
    AnalyticsValidationError,
    compute_ai_trend_preview,
)
from health_api.application.today_service import (
    healthkit_preferred_installations,
    owner_today_settings,
)
from health_api.domain.ai import (
    AIContextEntry,
    AIContextPack,
    AIContextRequest,
)
from health_api.domain.daily_rollups import DailyProvenance, MetricSummaryV1, summarize_today
from health_api.domain.schemas import (
    EventSchemaV1,
    ObservationSchemaV1,
    validate_iana_timezone,
)
from health_api.persistence.models import (
    EventObservationLink,
    HealthObject,
    Source,
)
from sqlalchemy import (
    and_,
    func,
    select,
    text,
)
from sqlalchemy.orm import Session


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


def _append_budgeted_entries(pack: AIContextPack, rows: list[Any]) -> bool:
    """Project only admitted rows and retain entries that fit both pack bounds."""
    critical_omitted = False
    for row in rows:
        if len(pack.entries) >= MAX_CONTEXT_ENTRIES:
            pack.omitted_by_budget += 1
            pack.truncated = True
            critical_omitted |= row.priority == 0
            continue
        entry = _context_entry(row)
        pack.entries.append(entry)
        if _set_serialized_size(pack) > MAX_CONTEXT_BYTES:
            pack.entries.pop()
            pack.omitted_by_budget += 1
            pack.truncated = True
            critical_omitted |= row.priority == 0
            _set_serialized_size(pack)
    _filter_relationships_to_included_entries(pack.entries)
    _set_serialized_size(pack)
    return critical_omitted


def _today_summaries(
    session: Session,
    owner_id: UUID,
    entries: list[AIContextEntry],
    local_date: date,
    timezone: str,
) -> list[MetricSummaryV1]:
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
    selection_rows = cast(
        list[tuple[UUID, str, str, dict[str, Any], int]],
        session.execute(
            select(
                HealthObject.id,
                Source.source_kind,
                HealthObject.confirmation_status,
                HealthObject.metadata_json,
                HealthObject.revision,
            )
            .join(
                Source,
                and_(Source.owner_id == HealthObject.owner_id, Source.id == HealthObject.source_id),
            )
            .where(HealthObject.owner_id == owner_id, HealthObject.id.in_(included_ids))
        ).all(),
    )
    provenance = {
        object_id: DailyProvenance(
            source_kind=source_kind,
            confirmation_status=confirmation_status,
            metadata=metadata if isinstance(metadata, dict) else {},
            revision=revision,
        )
        for object_id, source_kind, confirmation_status, metadata, revision in selection_rows
    }
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
    return summarize_today(
        events,
        observations,
        local_date,
        timezone,
        provenance=provenance,
        preferred_installations=healthkit_preferred_installations(session, owner_id),
    )


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
        .order_by(*context_candidate_order(candidates))
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
    critical_omitted = _append_budgeted_entries(pack, rows)
    if critical_omitted:
        raise ValueError("Eligible safety constraints do not fit in the context preview budget.")
    if "today_summaries" in request.sections and {"event", "observation"}.intersection(
        request.resource_types
    ):
        pack.today_summaries = _today_summaries(
            session, owner_id, pack.entries, pack.today_summary_date, timezone
        )
    if "trends" in request.sections and request.trend_metric is not None:
        trend_start = pack.today_summary_date - timedelta(days=request.lookback_days)
        try:
            pack.trend_summary = compute_ai_trend_preview(
                session,
                owner_id,
                request.trend_metric,
                trend_start,
                pack.today_summary_date,
                timezone,
                excluded_object_ids=set(request.excluded_object_ids),
                as_of=as_of,
            )
        except AnalyticsValidationError as exc:
            raise ValueError(str(exc)) from exc
    counts: dict[str, int] = {}
    while True:
        counts.clear()
        for entry in pack.entries:
            counts[entry.object_type] = counts.get(entry.object_type, 0) + 1
        if pack.trend_summary is not None:
            counts["trends"] = 1
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
    if _serialized_size(pack) > MAX_CONTEXT_BYTES:
        raise ValueError("Trend context does not fit the preview budget; narrow the request.")
    if final_size > MAX_CONTEXT_BYTES:
        raise ValueError("Context preview exceeds the maximum serialized size.")
    pack.omitted_by_budget = max(eligible_total - excluded_eligible_count - len(pack.entries), 0)
    pack.truncated = pack.omitted_by_budget > 0
    _set_serialized_size(pack)
    return pack
