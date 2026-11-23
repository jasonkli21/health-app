"""Add an insert-only Health dispatch submission journal."""

import sqlalchemy as sa
from alembic import op

revision = "20261123d101"
down_revision = "20261122f5b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "health_dispatch_intents",
        sa.Column(
            "original_key",
            sa.Uuid(),
            sa.ForeignKey("r5_preview_wire_bindings.original_key", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "create_key",
            sa.Uuid(),
            sa.ForeignKey("r5_preview_wire_bindings.original_key", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Uuid(), unique=True, nullable=False),
        sa.Column("root", sa.Uuid(), unique=True, nullable=False),
        sa.Column("binding_digest", sa.String(64), nullable=False),
        sa.Column("body_digest", sa.String(64), nullable=False),
        sa.Column("confirmation_digest", sa.String(64), nullable=False),
        sa.Column("create_receipt_digest", sa.String(64), nullable=False),
        sa.Column("create_response_digest", sa.String(64), nullable=False),
        sa.Column("create_version", sa.String(64), nullable=False),
        sa.Column("create_signer", sa.String(96), nullable=False),
        sa.Column("create_kid", sa.String(256), nullable=False),
        sa.Column("preview_receipt_digest", sa.String(64), nullable=False),
        sa.Column("preview_response_digest", sa.String(64), nullable=False),
        sa.Column("preview_version", sa.String(64), nullable=False),
        sa.Column("preview_signer", sa.String(96), nullable=False),
        sa.Column("preview_kid", sa.String(256), nullable=False),
        sa.Column("continuity_generation", sa.BigInteger(), nullable=False),
        sa.Column(
            "submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("continuity_generation > 0", name="ck_health_dispatch_generation"),
        sa.CheckConstraint(
            "create_version = 'health-application-plan-create-receipt-v1' "
            "AND preview_version = 'health-application-plan-preview-receipt-v1' "
            "AND create_signer = 'urn:fixture:pas:health-preview' "
            "AND preview_signer = 'urn:fixture:pas:health-preview'",
            name="ck_health_dispatch_provenance",
        ),
        sa.CheckConstraint(
            "binding_digest ~ '^[0-9a-f]{64}$' AND body_digest ~ '^[0-9a-f]{64}$' "
            "AND confirmation_digest ~ '^[0-9a-f]{64}$' "
            "AND create_receipt_digest ~ '^[0-9a-f]{64}$' "
            "AND create_response_digest ~ '^[0-9a-f]{64}$' "
            "AND preview_receipt_digest ~ '^[0-9a-f]{64}$' "
            "AND preview_response_digest ~ '^[0-9a-f]{64}$'",
            name="ck_health_dispatch_digests",
        ),
    )
    op.create_index("ix_health_dispatch_intents_owner_id", "health_dispatch_intents", ["owner_id"])
    op.execute(
        """
        CREATE FUNCTION enforce_health_dispatch_intent() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF EXISTS (SELECT 1 FROM users WHERE id = OLD.owner_id AND lifecycle = 'active') THEN
                    RAISE EXCEPTION 'Active Health dispatch intent cannot be deleted';
                END IF;
                RETURN OLD;
            END IF;
            IF TG_OP = 'UPDATE' OR NOT EXISTS (
                SELECT 1 FROM r5_preview_wire_bindings AS p
                JOIN r5_preview_reservations AS pr ON pr.original_key = p.original_key
                JOIN r5_preview_wire_bindings AS c ON c.original_key = NEW.create_key
                JOIN r5_preview_reservations AS cr ON cr.original_key = c.original_key
                WHERE p.original_key = NEW.original_key AND pr.operation = 'preview'
                    AND cr.operation = 'create' AND pr.intent_id = cr.intent_id
                    AND p.owner_id = NEW.owner_id AND c.owner_id = NEW.owner_id
                    AND p.pas_owner_id = c.pas_owner_id AND p.conversation_id = NEW.conversation_id
            ) THEN
                RAISE EXCEPTION 'Health dispatch intent is invalid or immutable';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_health_dispatch_intent BEFORE INSERT OR UPDATE OR DELETE "
        "ON health_dispatch_intents FOR EACH ROW EXECUTE FUNCTION enforce_health_dispatch_intent()"
    )
    op.execute(
        "CREATE TRIGGER trg_health_dispatch_active BEFORE INSERT ON health_dispatch_intents "
        "FOR EACH ROW EXECUTE FUNCTION enforce_active_owner_write()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE health_dispatch_intents IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT 1 FROM health_dispatch_intents LIMIT 1")):
        raise RuntimeError("Cannot discard retained Health dispatch intents")
    op.drop_table("health_dispatch_intents")
    op.execute("DROP FUNCTION enforce_health_dispatch_intent()")
