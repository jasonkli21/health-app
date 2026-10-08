"""Permission-safe resource search and deterministic pagination."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from health_api.application.ai_context_admission import _eligible_candidates
from health_api.application.ai_context_contracts import SEARCH_MAX_LOOKBACK_DAYS
from health_api.application.ai_context_projection import _excerpt, _payload_search_value
from health_api.application.ai_context_ranking import search_candidate_order
from health_api.domain.ai import (
    AIResourceType,
    AISearchResult,
)
from health_api.domain.schemas import (
    validate_iana_timezone,
)
from sqlalchemy import (
    and_,
    or_,
    select,
    text,
)
from sqlalchemy.orm import Session


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
    statement = statement.order_by(*search_candidate_order(candidates)).limit(limit + 1)
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
            excerpt=_excerpt(row.title, row.notes, _payload_search_value(row.payload), query),
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
