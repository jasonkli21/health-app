"""Add bounded full-text search indexes for Assistant retrieval.

Revision ID: f5c0a1e2d3b4
Revises: b8a125fec731
Create Date: 2026-10-05 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f5c0a1e2d3b4"
down_revision: str | None = "b8a125fec731"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_health_objects_ai_search ON health_objects USING gin "
        "(to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(notes, '')))"
    )
    for table in ("profile_items", "events", "observations", "planning_resources"):
        op.execute(
            f"CREATE INDEX ix_{table}_ai_search ON {table} USING gin "
            "(to_tsvector('simple', payload::text))"
        )


def downgrade() -> None:
    for table in ("planning_resources", "observations", "events", "profile_items"):
        op.execute(f"DROP INDEX ix_{table}_ai_search")
    op.execute("DROP INDEX ix_health_objects_ai_search")
