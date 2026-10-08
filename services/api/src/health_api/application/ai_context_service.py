"""Stable local Health context preview and search application façade."""

from __future__ import annotations

from health_api.application.ai_context_admission import (
    _candidate_branch,
    _eligibility_conditions,
    _eligible_candidates,
)
from health_api.application.ai_context_contracts import (
    MAX_CONTEXT_BYTES,
    MAX_CONTEXT_CANDIDATES,
    MAX_CONTEXT_ENTRIES,
    SEARCH_MAX_LOOKBACK_DAYS,
)
from health_api.application.ai_context_pack import (
    _serialized_size,
    _set_serialized_size,
    _today_summaries,
    build_ai_context,
)
from health_api.application.ai_context_projection import (
    _context_entry,
    _excerpt,
    _filter_relationships_to_included_entries,
    _nested_text,
    _payload_search_expression,
    _payload_search_projection,
    _payload_search_value,
)
from health_api.application.ai_context_ranking import (
    _common_vector,
    _payload_vector,
    _relevance_expression,
    _search_match_expression,
    context_candidate_order,
    search_candidate_order,
)
from health_api.application.ai_context_search import search_ai_resources

__all__ = [
    "MAX_CONTEXT_BYTES",
    "MAX_CONTEXT_CANDIDATES",
    "MAX_CONTEXT_ENTRIES",
    "SEARCH_MAX_LOOKBACK_DAYS",
    "_candidate_branch",
    "_common_vector",
    "_context_entry",
    "_eligibility_conditions",
    "_eligible_candidates",
    "_excerpt",
    "_filter_relationships_to_included_entries",
    "_nested_text",
    "_payload_search_expression",
    "_payload_search_projection",
    "_payload_search_value",
    "_payload_vector",
    "_relevance_expression",
    "_search_match_expression",
    "_serialized_size",
    "_set_serialized_size",
    "_today_summaries",
    "build_ai_context",
    "context_candidate_order",
    "search_ai_resources",
    "search_candidate_order",
]
