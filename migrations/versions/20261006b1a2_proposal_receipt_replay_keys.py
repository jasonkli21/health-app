"""Allow accepted replay keys to bind to one proposal result."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261006b1a2"
down_revision: str | Sequence[str] | None = ("e7f6a5b4c3d2", "f5c0a1e2d3b4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_action_command_receipts_proposal_revision",
        "action_command_receipts",
        type_="unique",
    )


def downgrade() -> None:
    connection = op.get_bind()
    duplicate_keys = connection.scalar(
        sa.text(
            "SELECT 1 FROM action_command_receipts "
            "GROUP BY owner_id, proposal_id, proposal_revision "
            "HAVING count(*) > 1 LIMIT 1"
        )
    )
    if duplicate_keys:
        raise RuntimeError(
            "refusing to discard alternate proposal receipt keys during downgrade"
        )
    op.create_unique_constraint(
        "uq_action_command_receipts_proposal_revision",
        "action_command_receipts",
        ["owner_id", "proposal_id", "proposal_revision"],
    )
