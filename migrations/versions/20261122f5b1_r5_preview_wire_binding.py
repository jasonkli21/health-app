"""Add exact wire bindings without granting authority to legacy reservations."""

import sqlalchemy as sa
from alembic import op

revision = "20261122f5b1"
down_revision = "20261122f5a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "r5_preview_wire_bindings",
        sa.Column(
            "original_key",
            sa.Uuid(),
            sa.ForeignKey("r5_preview_reservations.original_key", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("pas_owner_id", sa.String(36), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.Uuid()),
        sa.CheckConstraint("pas_owner_id ~ '^usr_[0-9a-f]{32}$'", name="ck_r5_wire_owner_format"),
        sa.CheckConstraint("request_digest ~ '^[0-9a-f]{64}$'", name="ck_r5_wire_digest"),
    )
    op.create_index(
        "ix_r5_preview_wire_bindings_owner_id", "r5_preview_wire_bindings", ["owner_id"]
    )
    op.execute(
        """
        CREATE FUNCTION enforce_r5_preview_wire_binding() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'UPDATE' OR NOT EXISTS (
                SELECT 1 FROM r5_preview_reservations AS r
                WHERE r.original_key = NEW.original_key AND r.owner_id = NEW.owner_id
                    AND (
                        (r.operation = 'create' AND NEW.conversation_id IS NULL
                         AND r.request_digest = NEW.request_digest)
                        OR (r.operation = 'preview' AND NEW.conversation_id IS NOT NULL)
                    )
            ) THEN
                RAISE EXCEPTION 'R5 preview wire binding is invalid or immutable';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_r5_preview_wire_binding_match BEFORE INSERT OR UPDATE "
        "ON r5_preview_wire_bindings FOR EACH ROW EXECUTE FUNCTION enforce_r5_preview_wire_binding()"
    )
    op.execute(
        "CREATE TRIGGER trg_r5_preview_wire_binding_active BEFORE INSERT ON r5_preview_wire_bindings "
        "FOR EACH ROW EXECUTE FUNCTION enforce_active_owner_write()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE r5_preview_wire_bindings IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT 1 FROM r5_preview_wire_bindings LIMIT 1")):
        raise RuntimeError("Cannot discard retained R5 preview wire bindings")
    op.drop_table("r5_preview_wire_bindings")
    op.execute("DROP FUNCTION enforce_r5_preview_wire_binding()")
