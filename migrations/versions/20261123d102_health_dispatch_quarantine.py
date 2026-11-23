"""Retain a one-way quarantine on a submitted Health attempt."""

import sqlalchemy as sa
from alembic import op

revision = "20261123d102"
down_revision = "20261123d101"
branch_labels = None
depends_on = None


def _enforce_dispatch_intent(quarantine_check: str) -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION enforce_health_dispatch_intent() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF EXISTS (SELECT 1 FROM users WHERE id = OLD.owner_id AND lifecycle = 'active') THEN
                    RAISE EXCEPTION 'Active Health dispatch intent cannot be deleted';
                END IF;
                RETURN OLD;
            END IF;
            {quarantine_check}
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


def upgrade() -> None:
    op.add_column(
        "health_dispatch_intents",
        sa.Column("quarantined_at", sa.DateTime(timezone=True)),
    )
    _enforce_dispatch_intent(
        """
        IF TG_OP = 'UPDATE' AND OLD.quarantined_at IS NULL
            AND NEW.quarantined_at IS NOT NULL
            AND (to_jsonb(OLD) - 'quarantined_at') = (to_jsonb(NEW) - 'quarantined_at')
        THEN
            RETURN NEW;
        END IF;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE health_dispatch_intents IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(
        sa.text(
            "SELECT 1 FROM health_dispatch_intents WHERE quarantined_at IS NOT NULL LIMIT 1"
        )
    ):
        raise RuntimeError("Cannot discard retained Health dispatch quarantines")
    _enforce_dispatch_intent("")
    op.drop_column("health_dispatch_intents", "quarantined_at")
