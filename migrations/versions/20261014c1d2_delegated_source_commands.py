"""Owner-fenced source commands participate in canonical erasure inventory."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261014c1d2"
down_revision = "20261007b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delegated_source_commands",
        sa.Column("command_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("command", JSONB, nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_delegated_source_commands_owner_id", "delegated_source_commands", ["owner_id"]
    )
    op.execute(
        "CREATE TRIGGER trg_delegated_source_commands_active_owner_write "
        "BEFORE INSERT OR UPDATE ON delegated_source_commands "
        "FOR EACH ROW EXECUTE FUNCTION enforce_active_owner_write()"
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT 1 FROM delegated_source_commands LIMIT 1")):
        raise RuntimeError("Cannot discard retained delegated task recovery state")
    op.drop_table("delegated_source_commands")
