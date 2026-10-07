"""Add HealthKit aggregate ordering and deletion-before-create identities."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261007a0b1"
down_revision: str | Sequence[str] | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE observations ADD CONSTRAINT ck_observations_steps_date_only "
        "CHECK (metric_key <> 'steps' OR "
        "(time_precision = 'date_only' AND interval_end IS NULL)) NOT VALID"
    )
    op.execute(
        "ALTER TABLE observations ADD CONSTRAINT ck_observations_steps_numeric_bound "
        "CHECK (metric_key <> 'steps' OR "
        "(numeric_value >= 0 AND numeric_value <= 1e300)) NOT VALID"
    )
    op.add_column(
        "healthkit_import_identities",
        sa.Column(
            "source_revision", sa.BigInteger(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "healthkit_import_identities",
        sa.Column(
            "user_archived", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.alter_column(
        "healthkit_import_identities",
        "object_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_healthkit_identity_source_revision",
        "healthkit_import_identities",
        "source_revision BETWEEN 0 AND 9007199254740991",
    )
    op.create_check_constraint(
        "ck_healthkit_identity_object_or_tombstone",
        "healthkit_import_identities",
        "object_id IS NOT NULL OR tombstoned_at IS NOT NULL",
    )


def downgrade() -> None:
    connection = op.get_bind()
    unrepresentable_rows = connection.scalar(
        sa.text(
            "SELECT 1 FROM healthkit_import_identities "
            "WHERE object_id IS NULL OR source_revision > 0 OR user_archived LIMIT 1"
        )
    )
    if unrepresentable_rows:
        raise RuntimeError(
            "refusing to discard HealthKit deletion identities or aggregate ordering revisions"
        )
    op.drop_constraint(
        "ck_observations_steps_numeric_bound", "observations", type_="check"
    )
    op.drop_constraint("ck_observations_steps_date_only", "observations", type_="check")
    op.drop_constraint(
        "ck_healthkit_identity_object_or_tombstone",
        "healthkit_import_identities",
        type_="check",
    )
    op.drop_constraint(
        "ck_healthkit_identity_source_revision",
        "healthkit_import_identities",
        type_="check",
    )
    op.alter_column(
        "healthkit_import_identities",
        "object_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.drop_column("healthkit_import_identities", "user_archived")
    op.drop_column("healthkit_import_identities", "source_revision")
