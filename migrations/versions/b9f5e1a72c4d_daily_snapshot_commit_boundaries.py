"""Represent committed daily writes as complete snapshot boundaries.

Revision ID: b9f5e1a72c4d
Revises: 8e31c7c9a0b2
Create Date: 2026-10-04 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b9f5e1a72c4d"
down_revision: str | None = "8e31c7c9a0b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_health_object_revision_daily_sequence",
        "health_object_revisions",
        type_="unique",
    )
    op.create_table(
        "daily_snapshot_markers",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("daily_sequence", sa.Integer(), nullable=False),
        sa.CheckConstraint("daily_sequence >= 0", name="ck_daily_snapshot_markers_sequence"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_daily_snapshot_markers_owner",
        ),
        sa.PrimaryKeyConstraint("owner_id", "daily_sequence"),
    )
    # The old per-object counter assigned several sequence values inside a compound
    # transaction. Keep only the latest state as a legacy cursor boundary; the new
    # writer records one shared marker for each committed command.
    op.execute(
        sa.text(
            "INSERT INTO daily_snapshot_markers (owner_id, daily_sequence) "
            "SELECT id, 0 FROM users UNION SELECT id, daily_sequence FROM users "
            "WHERE daily_sequence > 0"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    duplicate_sequence = connection.scalar(
        sa.text(
            "SELECT 1 FROM health_object_revisions WHERE daily_sequence IS NOT NULL "
            "GROUP BY owner_id, daily_sequence HAVING count(*) > 1 LIMIT 1"
        )
    )
    if duplicate_sequence:
        raise RuntimeError("refusing to restore per-object snapshot sequences with shared markers")
    op.drop_table("daily_snapshot_markers")
    op.create_unique_constraint(
        "uq_health_object_revision_daily_sequence",
        "health_object_revisions",
        ["owner_id", "daily_sequence"],
    )
