"""Narrow Alembic comparison rules for PostgreSQL expression indexes."""

from __future__ import annotations

import re
from typing import Any, Protocol, cast

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import Index

_AI_PAYLOAD_INDEXES = {
    "ix_profile_items_ai_search": "profile_items",
    "ix_events_ai_search": "events",
    "ix_observations_ai_search": "observations",
    "ix_planning_resources_ai_search": "planning_resources",
}
_EXPECTED_AI_PAYLOAD_TOKENS = (
    "to_tsvector",
    "'simple'",
    ",",
    "payload",
    "-",
    "'related'",
    "-",
    "'items'",
    "-",
    "'linked_observation_ids'",
)


class _ExpressionCompiler(Protocol):
    def __call__(self, *, dialect: Any, compile_kwargs: dict[str, bool]) -> Any: ...


def _expression_tokens(index: Index) -> tuple[str, ...] | None:
    if len(index.expressions) != 1:
        return None
    index_expression = index.expressions[0]
    if isinstance(index_expression, str):
        expression = index_expression
    else:
        dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
        compile_expression = cast(_ExpressionCompiler, index_expression.compile)
        expression = str(
            compile_expression(dialect=dialect, compile_kwargs={"literal_binds": True})
        )
    expression = expression.replace('"', "")
    expression = re.sub(
        r"\b(?:profile_items|events|observations|planning_resources)\s*\.\s*",
        "",
        expression,
        flags=re.IGNORECASE,
    )
    expression = re.sub(r"::\s*(?:text|regconfig)\b", "", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\bCAST\s*\(", "(", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\s+AS\s+TEXT(?=\s*\))", "", expression, flags=re.IGNORECASE)
    tokens = re.findall(r"'(?:''|[^'])*'|[a-z_][a-z0-9_$]*|-|,", expression.lower())
    return tuple(tokens)


def _same_ai_payload_index(left: Index, right: Index, name: str) -> bool:
    table_name = _AI_PAYLOAD_INDEXES[name]
    left_table = left.table
    right_table = right.table
    if (
        left.name != name
        or right.name != name
        or left_table is None
        or right_table is None
        or left_table.name != table_name
        or right_table.name != table_name
        or left.unique != right.unique
        or left.dialect_options["postgresql"].get("using")
        != right.dialect_options["postgresql"].get("using")
        or left.dialect_options["postgresql"].get("where") is not None
        or right.dialect_options["postgresql"].get("where") is not None
    ):
        return False
    return (
        _expression_tokens(left) == _EXPECTED_AI_PAYLOAD_TOKENS
        and _expression_tokens(right) == _EXPECTED_AI_PAYLOAD_TOKENS
    )


def include_schema_object(
    obj: Any,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: Any | None,
) -> bool:
    """Ignore only equivalent renderings of four known GIN expressions.

    A metadata-only index or database-only index remains visible to Alembic,
    and any changed expression, method, uniqueness, or predicate is compared
    normally.
    """
    if type_ != "index" or name not in _AI_PAYLOAD_INDEXES or compare_to is None:
        return True
    metadata_index = compare_to if reflected else obj
    reflected_index = obj if reflected else compare_to
    if not isinstance(metadata_index, Index) or not isinstance(reflected_index, Index):
        return True
    return not _same_ai_payload_index(metadata_index, reflected_index, name)
