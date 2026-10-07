"""Add bounded account export/deletion status and freeze writes during erasure."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261007b1c2"
down_revision: str | Sequence[str] | None = "20261007a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_OWNER_TABLES = (
    "action_proposals",
    "daily_snapshot_markers",
    "healthkit_import_batches",
    "sources",
    "action_proposal_revisions",
    "health_objects",
    "healthkit_source_preferences",
    "action_command_receipts",
    "action_proposal_events",
    "analytics_artifacts",
    "events",
    "health_object_revisions",
    "health_relationships",
    "healthkit_import_identities",
    "observations",
    "planning_resources",
    "profile_items",
    "tracker_schema_versions",
    "analytics_evidence",
    "event_observation_links",
    "planning_links",
    "planning_schedule_identities",
    "planning_occurrence_overrides",
    "planning_schedules",
    "planning_occurrence_actions",
)


def upgrade() -> None:
    op.drop_constraint("ck_users_lifecycle", "users", type_="check")
    op.create_check_constraint(
        "ck_users_lifecycle",
        "users",
        "lifecycle IN ('active', 'disabled', 'deleting', 'erased')",
    )

    op.create_table(
        "owner_deletion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="running", nullable=False),
        sa.Column("error_code", sa.String(length=48), nullable=True),
        sa.Column(
            "requested_at",
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
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'failed', 'completed')",
            name="ck_owner_deletion_jobs_status",
        ),
        sa.CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)",
            name="ck_owner_deletion_jobs_completed_at",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR error_code IN "
            "('object_storage_unavailable', 'database_cleanup_failed')",
            name="ck_owner_deletion_jobs_error_code",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_owner_deletion_jobs_owner",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "id", name="uq_owner_deletion_jobs_owner_id"),
    )
    op.create_index(
        "ix_owner_deletion_jobs_owner_requested",
        "owner_deletion_jobs",
        ["owner_id", "requested_at"],
    )
    op.create_table(
        "owner_erasure_ledger",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "erased_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "retention_policy",
            sa.String(length=48),
            server_default="until_backup_policy_is_verified",
            nullable=False,
        ),
        sa.CheckConstraint(
            "retention_policy = 'until_backup_policy_is_verified'",
            name="ck_owner_erasure_ledger_retention_policy",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_owner_erasure_ledger_owner",
        ),
        sa.PrimaryKeyConstraint("owner_id"),
    )

    op.execute(
        "CREATE FUNCTION enforce_active_owner_write() RETURNS trigger AS $$ "
        "DECLARE owner_lifecycle text; BEGIN "
        "IF TG_OP = 'UPDATE' AND NEW.owner_id IS DISTINCT FROM OLD.owner_id THEN "
        "RAISE EXCEPTION 'owner cannot be changed' USING ERRCODE = '23514', "
        "CONSTRAINT = 'ck_owner_domain_writable'; END IF; "
        "SELECT lifecycle INTO owner_lifecycle FROM users "
        "WHERE id = NEW.owner_id FOR SHARE; "
        "IF owner_lifecycle IS DISTINCT FROM 'active' THEN "
        "RAISE EXCEPTION 'owner is not active' USING ERRCODE = '23514', "
        "CONSTRAINT = 'ck_owner_domain_writable'; END IF; "
        "RETURN NEW; END; $$ LANGUAGE plpgsql"
    )
    for table_name in _OWNER_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table_name}_active_owner_write "
            f"BEFORE INSERT OR UPDATE ON {table_name} "
            "FOR EACH ROW EXECUTE FUNCTION enforce_active_owner_write()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    retained_erasure = connection.scalar(sa.text("SELECT 1 FROM owner_erasure_ledger LIMIT 1"))
    deletion_jobs = connection.scalar(sa.text("SELECT 1 FROM owner_deletion_jobs LIMIT 1"))
    erased_users = connection.scalar(
        sa.text("SELECT 1 FROM users WHERE lifecycle IN ('deleting', 'erased') LIMIT 1")
    )
    if retained_erasure or deletion_jobs or erased_users:
        raise RuntimeError("refusing to remove owner erasure state or its write freeze")

    for table_name in _OWNER_TABLES:
        op.execute(f"DROP TRIGGER trg_{table_name}_active_owner_write ON {table_name}")
    op.execute("DROP FUNCTION enforce_active_owner_write()")
    op.drop_table("owner_erasure_ledger")
    op.drop_index("ix_owner_deletion_jobs_owner_requested", table_name="owner_deletion_jobs")
    op.drop_table("owner_deletion_jobs")
    op.drop_constraint("ck_users_lifecycle", "users", type_="check")
    op.create_check_constraint("ck_users_lifecycle", "users", "lifecycle IN ('active', 'disabled')")
