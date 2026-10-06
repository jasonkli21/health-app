"""Store typed proposals, immutable revisions, audit events, and receipts."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7f6a5b4c3d2"
down_revision: str | None = "6a0b1c2d3e4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "schema_version", sa.SmallInteger(), server_default="1", nullable=False
        ),
        sa.Column(
            "state", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column("origin_kind", sa.String(length=16), nullable=False),
        sa.Column(
            "origin_metadata",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("current_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_revision", sa.Integer(), nullable=True),
        sa.Column("rejected_by", sa.Uuid(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.String(length=500), nullable=True),
        sa.Column("result_json", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "last_validation_summary",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "schema_version = 1", name="ck_action_proposals_schema_version"
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'applied', 'rejected', 'expired', 'superseded')",
            name="ck_action_proposals_state",
        ),
        sa.CheckConstraint(
            "origin_kind IN ('user', 'ai')", name="ck_action_proposals_origin"
        ),
        sa.CheckConstraint("current_revision > 0", name="ck_action_proposals_revision"),
        sa.CheckConstraint(
            "length(content_hash) = 64", name="ck_action_proposals_hash"
        ),
        sa.CheckConstraint(
            "expires_at > created_at AND expires_at <= created_at + interval '7 days'",
            name="ck_action_proposals_expiry",
        ),
        sa.CheckConstraint(
            "(confirmed_by IS NULL) = (confirmed_at IS NULL)",
            name="ck_action_proposals_confirmation_pair",
        ),
        sa.CheckConstraint(
            "(rejected_by IS NULL) = (rejected_at IS NULL)",
            name="ck_action_proposals_rejection_pair",
        ),
        sa.CheckConstraint(
            "state <> 'applied' OR (confirmed_by = owner_id AND applied_at IS NOT NULL AND applied_revision IS NOT NULL AND result_json IS NOT NULL)",
            name="ck_action_proposals_applied_result",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_action_proposals_owner",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_action_proposals"),
        sa.UniqueConstraint("owner_id", "id", name="uq_action_proposals_owner_id"),
    )
    op.create_index(
        "ix_action_proposals_owner_state_created",
        "action_proposals",
        ["owner_id", "state", "created_at", "id"],
    )

    op.create_table(
        "action_proposal_revisions",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision > 0", name="ck_action_proposal_revisions_revision"
        ),
        sa.CheckConstraint(
            "schema_version = 1", name="ck_action_proposal_revisions_schema_version"
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64", name="ck_action_proposal_revisions_hash"
        ),
        sa.CheckConstraint(
            "actor_id = owner_id", name="ck_action_proposal_revisions_actor"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "proposal_id"],
            ["action_proposals.owner_id", "action_proposals.id"],
            ondelete="CASCADE",
            name="fk_action_proposal_revisions_owner_proposal",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_action_proposal_revisions_actor",
        ),
        sa.PrimaryKeyConstraint(
            "owner_id", "proposal_id", "revision", name="pk_action_proposal_revisions"
        ),
    )

    op.create_table(
        "action_proposal_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_revision", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "details",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "proposal_revision > 0", name="ck_action_proposal_events_revision"
        ),
        sa.CheckConstraint(
            "event IN ('created', 'edited', 'applied', 'rejected', 'expired')",
            name="ck_action_proposal_events_event",
        ),
        sa.CheckConstraint(
            "actor_id = owner_id", name="ck_action_proposal_events_actor"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "proposal_id", "proposal_revision"],
            [
                "action_proposal_revisions.owner_id",
                "action_proposal_revisions.proposal_id",
                "action_proposal_revisions.revision",
            ],
            ondelete="CASCADE",
            name="fk_action_proposal_events_revision",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_action_proposal_events_actor",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_action_proposal_events"),
    )
    op.create_index(
        "ix_action_proposal_events_owner_proposal_recorded",
        "action_proposal_events",
        ["owner_id", "proposal_id", "recorded_at", "id"],
    )

    op.create_table(
        "action_command_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_revision", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("result_json", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "proposal_revision > 0", name="ck_action_command_receipts_revision"
        ),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 1 AND 128",
            name="ck_action_command_receipts_key",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64", name="ck_action_command_receipts_hash"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "proposal_id", "proposal_revision"],
            [
                "action_proposal_revisions.owner_id",
                "action_proposal_revisions.proposal_id",
                "action_proposal_revisions.revision",
            ],
            ondelete="RESTRICT",
            name="fk_action_command_receipts_revision",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_action_command_receipts"),
        sa.UniqueConstraint(
            "owner_id", "idempotency_key", name="uq_action_command_receipts_owner_key"
        ),
        sa.UniqueConstraint(
            "owner_id",
            "proposal_id",
            "proposal_revision",
            name="uq_action_command_receipts_proposal_revision",
        ),
    )

    op.add_column(
        "health_object_revisions", sa.Column("proposal_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_health_object_revisions_owner_proposal",
        "health_object_revisions",
        "action_proposals",
        ["owner_id", "proposal_id"],
        ["owner_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    connection = op.get_bind()
    existing = connection.scalar(sa.text("SELECT 1 FROM action_proposals LIMIT 1"))
    if existing:
        raise RuntimeError("refusing to discard proposal history or command receipts")
    op.drop_constraint(
        "fk_health_object_revisions_owner_proposal",
        "health_object_revisions",
        type_="foreignkey",
    )
    op.drop_column("health_object_revisions", "proposal_id")
    op.drop_table("action_command_receipts")
    op.drop_index(
        "ix_action_proposal_events_owner_proposal_recorded",
        table_name="action_proposal_events",
    )
    op.drop_table("action_proposal_events")
    op.drop_table("action_proposal_revisions")
    op.drop_index(
        "ix_action_proposals_owner_state_created", table_name="action_proposals"
    )
    op.drop_table("action_proposals")
