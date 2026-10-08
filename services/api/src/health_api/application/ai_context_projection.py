"""Safe projection of admitted Health rows into local preview/search fields."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from health_api.domain.ai import (
    AIContextEntry,
)


def _payload_search_expression(payload: Any) -> Any:
    # Relationship labels and identifiers are not search evidence. They are
    # omitted from matching/ranking, as well as from displayed excerpts.
    return payload.op("-")("related").op("-")("items").op("-")("linked_observation_ids")


def _payload_search_projection(payload: Any) -> Any:
    """Backwards-compatible name for the SQL-side relationship-safe projection."""
    return _payload_search_expression(payload)


def _payload_search_value(payload: Any) -> Any:
    """Apply the SQL search projection to an already-decoded JSON payload."""
    if not isinstance(payload, dict):
        return payload
    excluded = {"related", "items", "linked_observation_ids"}
    return {key: value for key, value in payload.items() if key not in excluded}


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
    metadata = row.health_metadata if isinstance(row.health_metadata, dict) else {}
    healthkit_interpretation = {
        key.removeprefix("healthkit_"): metadata[key]
        for key in (
            "healthkit_resource_type",
            "healthkit_sleep_stage",
            "healthkit_aggregation_method_version",
            "healthkit_sample_count",
            "healthkit_minimum",
            "healthkit_maximum",
            "healthkit_coverage_start",
            "healthkit_coverage_end",
        )
        if key in metadata
    }
    if healthkit_interpretation:
        content["healthkit_interpretation"] = healthkit_interpretation
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


def _nested_text(value: Any, key: str | None = None) -> Iterator[str]:
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
