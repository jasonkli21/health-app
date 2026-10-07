"""Add owner-scoped HealthKit batch receipts and source identities."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "f7c8d9e0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_observations_metric", "observations", type_="check")
    op.create_check_constraint(
        "ck_observations_metric",
        "observations",
        "metric_key IN ('weight', 'temperature', 'systolic_pressure', "
        "'diastolic_pressure', 'pulse', 'steps', 'resting_heart_rate', "
        "'heart_rate_summary', 'symptom_severity', 'custom')",
    )
    op.drop_constraint("ck_observations_metric_unit", "observations", type_="check")
    op.create_check_constraint(
        "ck_observations_metric_unit",
        "observations",
        "(metric_key = 'weight' AND unit IN ('kg', 'lb')) OR "
        "(metric_key = 'temperature' AND unit IN ('C', 'F')) OR "
        "(metric_key IN ('systolic_pressure', 'diastolic_pressure') AND unit = 'mmHg') OR "
        "(metric_key IN ('pulse', 'resting_heart_rate', 'heart_rate_summary') AND unit = 'bpm') OR "
        "(metric_key = 'steps' AND unit = 'steps') OR "
        "(metric_key = 'symptom_severity' AND unit = 'score') OR "
        "(metric_key = 'custom' AND unit = 'custom')",
    )
    op.create_table(
        "healthkit_import_batches",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("device_installation_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unchanged_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tombstoned_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("correction_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("conflict_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "resource_type IN ('workouts', 'sleep', 'steps', 'weight', "
            "'resting_heart_rate', 'heart_rate_summary')",
            name="ck_healthkit_batches_resource_type",
        ),
        sa.CheckConstraint(
            "policy_version = 'healthkit-v1'", name="ck_healthkit_batches_policy"
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64", name="ck_healthkit_batches_hash"
        ),
        sa.CheckConstraint(
            "created_count >= 0 AND updated_count >= 0 AND unchanged_count >= 0 AND "
            "tombstoned_count >= 0 AND correction_count >= 0 AND conflict_count >= 0",
            name="ck_healthkit_batches_counts",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_healthkit_batches_owner",
        ),
        sa.PrimaryKeyConstraint("owner_id", "batch_id"),
    )
    op.create_index(
        "ix_healthkit_batches_owner_created",
        "healthkit_import_batches",
        ["owner_id", "created_at"],
    )
    op.create_table(
        "healthkit_import_identities",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "platform",
            sa.String(length=24),
            server_default="apple_healthkit",
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("source_sample_id", sa.String(length=256), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("device_installation_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "is_aggregate", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("aggregate_date", sa.Date(), nullable=True),
        sa.Column("aggregate_timezone", sa.String(length=64), nullable=True),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column(
            "analytics_selected", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column("tombstoned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "platform = 'apple_healthkit'", name="ck_healthkit_identity_platform"
        ),
        sa.CheckConstraint(
            "resource_type IN ('workouts', 'sleep', 'steps', 'weight', "
            "'resting_heart_rate', 'heart_rate_summary')",
            name="ck_healthkit_identity_resource_type",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64", name="ck_healthkit_identity_hash"
        ),
        sa.CheckConstraint(
            "policy_version = 'healthkit-v1'", name="ck_healthkit_identity_policy"
        ),
        sa.CheckConstraint(
            "(is_aggregate AND aggregate_date IS NOT NULL AND aggregate_timezone IS NOT NULL) OR "
            "(NOT is_aggregate AND aggregate_date IS NULL AND aggregate_timezone IS NULL AND analytics_selected)",
            name="ck_healthkit_identity_aggregate_shape",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_healthkit_identity_owner",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_healthkit_identity_object",
        ),
        sa.PrimaryKeyConstraint(
            "owner_id", "platform", "resource_type", "source_sample_id"
        ),
        sa.UniqueConstraint(
            "owner_id", "object_id", name="uq_healthkit_identity_object"
        ),
    )
    op.create_index(
        "ix_healthkit_identity_owner_aggregate",
        "healthkit_import_identities",
        ["owner_id", "resource_type", "aggregate_date", "analytics_selected"],
    )
    op.create_table(
        "healthkit_source_preferences",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("device_installation_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "resource_type IN ('steps', 'heart_rate_summary')",
            name="ck_healthkit_preferences_resource_type",
        ),
        sa.CheckConstraint("revision > 0", name="ck_healthkit_preferences_revision"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_healthkit_preferences_owner",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "source_id"],
            ["sources.owner_id", "sources.id"],
            ondelete="RESTRICT",
            name="fk_healthkit_preferences_source",
        ),
        sa.PrimaryKeyConstraint("owner_id", "resource_type"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    imported_rows = connection.scalar(
        sa.text("SELECT 1 FROM healthkit_import_identities LIMIT 1")
    )
    batches = connection.scalar(
        sa.text("SELECT 1 FROM healthkit_import_batches LIMIT 1")
    )
    if imported_rows or batches:
        raise RuntimeError(
            "refusing to discard imported HealthKit identities or batch history"
        )
    op.drop_table("healthkit_source_preferences")
    op.drop_index(
        "ix_healthkit_identity_owner_aggregate",
        table_name="healthkit_import_identities",
    )
    op.drop_table("healthkit_import_identities")
    op.drop_index(
        "ix_healthkit_batches_owner_created", table_name="healthkit_import_batches"
    )
    op.drop_table("healthkit_import_batches")
    op.drop_constraint("ck_observations_metric_unit", "observations", type_="check")
    op.create_check_constraint(
        "ck_observations_metric_unit",
        "observations",
        "(metric_key = 'weight' AND unit IN ('kg', 'lb')) OR "
        "(metric_key = 'temperature' AND unit IN ('C', 'F')) OR "
        "(metric_key IN ('systolic_pressure', 'diastolic_pressure') AND unit = 'mmHg') OR "
        "(metric_key = 'pulse' AND unit = 'bpm') OR "
        "(metric_key = 'symptom_severity' AND unit = 'score') OR "
        "(metric_key = 'custom' AND unit = 'custom')",
    )
    op.drop_constraint("ck_observations_metric", "observations", type_="check")
    op.create_check_constraint(
        "ck_observations_metric",
        "observations",
        "metric_key IN ('weight', 'temperature', 'systolic_pressure', "
        "'diastolic_pressure', 'pulse', 'symptom_severity', 'custom')",
    )
