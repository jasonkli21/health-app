"""Keep relationship metadata out of AI full text matching."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "6a0b1c2d3e4f"
down_revision: str | None = "f5c0a1e2d3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("profile_items", "events", "observations", "planning_resources"):
        op.execute(f"DROP INDEX ix_{table}_ai_search")
        op.execute(
            f"CREATE INDEX ix_{table}_ai_search ON {table} USING gin "
            "(to_tsvector('simple', (payload - 'related' - 'items' - 'linked_observation_ids')::text))"
        )


def downgrade() -> None:
    for table in ("planning_resources", "observations", "events", "profile_items"):
        op.execute(f"DROP INDEX ix_{table}_ai_search")
        op.execute(
            f"CREATE INDEX ix_{table}_ai_search ON {table} USING gin "
            "(to_tsvector('simple', payload::text))"
        )
