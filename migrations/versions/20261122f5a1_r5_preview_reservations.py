"""Reserve original operation keys without enabling R5 transport or receipt adoption."""

import sqlalchemy as sa
from alembic import op

revision = "20261122f5a1"
down_revision = "20261014c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "r5_preview_reservations",
        sa.Column("original_key", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("intent_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(7), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("object_revision", sa.Integer(), nullable=False),
        sa.Column("binding_digest", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "intent_id", "operation", name="uq_r5_preview_reservations_intent_operation"
        ),
        sa.CheckConstraint("operation IN ('create', 'preview')", name="ck_r5_preview_operation"),
        sa.CheckConstraint("object_revision > 0", name="ck_r5_preview_revision"),
        sa.CheckConstraint(
            "binding_digest ~ '^[0-9a-f]{64}$'", name="ck_r5_preview_binding_digest"
        ),
        sa.CheckConstraint(
            "(operation = 'create' AND request_digest IS NOT NULL "
            "AND request_digest ~ '^[0-9a-f]{64}$') "
            "OR (operation = 'preview' AND request_digest IS NULL)",
            name="ck_r5_preview_request_digest",
        ),
    )
    op.create_index("ix_r5_preview_reservations_owner_id", "r5_preview_reservations", ["owner_id"])
    op.execute(
        "CREATE TRIGGER trg_r5_preview_reservations_active_owner_write "
        "BEFORE INSERT ON r5_preview_reservations "
        "FOR EACH ROW EXECUTE FUNCTION enforce_active_owner_write()"
    )
    op.execute(
        "CREATE FUNCTION reject_r5_preview_reservation_update() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'R5 preview reservations are immutable'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER trg_r5_preview_reservations_immutable "
        "BEFORE UPDATE ON r5_preview_reservations "
        "FOR EACH ROW EXECUTE FUNCTION reject_r5_preview_reservation_update()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE r5_preview_reservations IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT 1 FROM r5_preview_reservations LIMIT 1")):
        raise RuntimeError("Cannot discard retained R5 original-key reservations")
    op.drop_table("r5_preview_reservations")
    op.execute("DROP FUNCTION reject_r5_preview_reservation_update()")
