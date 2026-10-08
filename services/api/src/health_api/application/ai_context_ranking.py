"""PostgreSQL text ranking and stable candidate ordering."""

from __future__ import annotations

from typing import Any

from health_api.application.ai_context_projection import _payload_search_expression
from health_api.persistence.models import (
    HealthObject,
)
from sqlalchemy import (
    Text,
    cast,
    func,
    literal_column,
    or_,
)


def _relevance_expression(common_vector: Any, payload_vector: Any, task_query: Any) -> Any:
    return func.greatest(
        func.ts_rank_cd(common_vector, task_query),
        func.ts_rank_cd(payload_vector, task_query),
    )


def _search_match_expression(common_vector: Any, payload_vector: Any, search_query: Any) -> Any:
    return or_(common_vector.op("@@")(search_query), payload_vector.op("@@")(search_query))


def context_candidate_order(candidates: Any) -> tuple[Any, ...]:
    return (
        candidates.c.priority.asc(),
        candidates.c.context_priority.desc(),
        candidates.c.confirmation_priority.asc(),
        candidates.c.relevance.desc(),
        candidates.c.recorded_at.desc(),
        candidates.c.object_id,
    )


def search_candidate_order(candidates: Any) -> tuple[Any, ...]:
    return (candidates.c.recorded_at.desc(), candidates.c.object_id.asc())


def _common_vector() -> Any:
    return func.to_tsvector(
        literal_column("'simple'"),
        func.coalesce(HealthObject.title, literal_column("''"))
        .op("||")(literal_column("' '"))
        .op("||")(func.coalesce(HealthObject.notes, literal_column("''"))),
    )


def _payload_vector(payload: Any) -> Any:
    return func.to_tsvector(
        literal_column("'simple'"), cast(_payload_search_expression(payload), Text)
    )
