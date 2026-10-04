"""Add a unique verified provider identity mapping.

Revision ID: c3721f5a9a01
Revises: b9f5e1a72c4d
Create Date: 2026-10-04 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3721f5a9a01"
down_revision: str | None = "b9f5e1a72c4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_identities",
        sa.Column("issuer", sa.String(length=256), nullable=False),
        sa.Column("subject", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(issuer) BETWEEN 1 AND 256", name="ck_provider_identity_issuer"
        ),
        sa.CheckConstraint(
            "char_length(subject) BETWEEN 1 AND 128", name="ck_provider_identity_subject"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("issuer", "subject"),
        sa.UniqueConstraint("user_id", name="uq_provider_identities_user"),
    )


def downgrade() -> None:
    op.drop_table("provider_identities")
