from __future__ import annotations

from health_api.persistence.migration_compare import include_schema_object
from sqlalchemy import Column, MetaData, Table, Text, cast, func, literal_column, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import Index


def _metadata_index() -> Index:
    table = Table("events", MetaData(), Column("payload", JSONB))
    projection = (
        table.c.payload.op("-")(literal_column("'related'"))
        .op("-")(literal_column("'items'"))
        .op("-")(literal_column("'linked_observation_ids'"))
    )
    index = Index(
        "ix_events_ai_search",
        func.to_tsvector(literal_column("'simple'"), cast(projection, Text)),
        _table=table,
        postgresql_using="gin",
    )
    return index


def _reflected_index(expression: str, *, using: str = "gin") -> Index:
    table = Table("events", MetaData(), Column("payload", JSONB))
    index = Index("ix_events_ai_search", text(expression), _table=table, postgresql_using=using)
    return index


def test_alembic_ignores_only_equivalent_postgresql_cast_rendering() -> None:
    metadata_index = _metadata_index()
    reflected_index = _reflected_index(
        "to_tsvector('simple'::regconfig, (((payload - 'related'::text) "
        "- 'items'::text) - 'linked_observation_ids'::text)::text)"
    )

    assert (
        include_schema_object(
            metadata_index,
            metadata_index.name,
            "index",
            False,
            reflected_index,
        )
        is False
    )
    assert (
        include_schema_object(
            reflected_index,
            reflected_index.name,
            "index",
            True,
            metadata_index,
        )
        is False
    )


def test_alembic_still_detects_missing_changed_or_differently_built_indexes() -> None:
    metadata_index = _metadata_index()
    changed_expression = _reflected_index("to_tsvector('simple', payload::text)")
    changed_method = _reflected_index(
        "to_tsvector('simple'::regconfig, ((payload - 'related') - 'items') "
        "- 'linked_observation_ids')",
        using="btree",
    )

    assert include_schema_object(metadata_index, metadata_index.name, "index", False, None)
    assert include_schema_object(
        metadata_index, metadata_index.name, "index", False, changed_expression
    )
    assert include_schema_object(
        metadata_index, metadata_index.name, "index", False, changed_method
    )
