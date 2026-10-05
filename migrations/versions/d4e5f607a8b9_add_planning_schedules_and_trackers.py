"""Add Phase 4 planning resources, schedules, and custom tracker versions.

Revision ID: d4e5f607a8b9
Revises: c3721f5a9a01
Create Date: 2026-10-05 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f607a8b9"
down_revision: str | None = "c3721f5a9a01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_health_objects_type", "health_objects", type_="check")
    op.drop_constraint("ck_health_objects_domain_type", "health_objects", type_="check")
    op.create_check_constraint(
        "ck_health_objects_type",
        "health_objects",
        "object_type IN ('profile_item', 'event', 'observation', 'goal', 'regimen', 'plan', "
        "'context', 'tracker_definition')",
    )
    op.create_check_constraint(
        "ck_health_objects_domain_type",
        "health_objects",
        "(object_type = 'profile_item' AND domain = 'profile') OR "
        "(object_type = 'event' AND domain IN ('nutrition', 'exercise', 'sleep', 'symptoms')) OR "
        "(object_type = 'observation' AND domain IN ('measurements', 'symptoms', 'nutrition', 'exercise', 'sleep')) OR "
        "(object_type IN ('goal', 'regimen', 'plan', 'context', 'tracker_definition') AND domain IN "
        "('planning', 'nutrition', 'exercise', 'sleep', 'symptoms', 'measurements', 'general'))",
    )

    op.alter_column(
        "observations", "numeric_value", existing_type=sa.Float(), nullable=True
    )
    op.add_column("observations", sa.Column("tracker_id", sa.Uuid(), nullable=True))
    op.add_column(
        "observations",
        sa.Column("tracker_schema_version", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "observations",
        sa.Column(
            "tracker_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.drop_constraint("ck_observations_metric", "observations", type_="check")
    op.create_check_constraint(
        "ck_observations_metric",
        "observations",
        "metric_key IN ('weight', 'temperature', 'systolic_pressure', 'diastolic_pressure', "
        "'pulse', 'symptom_severity', 'custom')",
    )
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
    op.drop_constraint("ck_observations_numeric_value", "observations", type_="check")
    op.create_check_constraint(
        "ck_observations_numeric_value",
        "observations",
        "(metric_key = 'custom' AND numeric_value IS NULL) OR "
        "(metric_key <> 'custom' AND numeric_value IS NOT NULL AND "
        "numeric_value > '-Infinity'::double precision AND numeric_value < 'Infinity'::double precision AND "
        "(metric_key <> 'symptom_severity' OR "
        "(numeric_value >= 0 AND numeric_value <= 10 AND numeric_value = trunc(numeric_value))))",
    )
    op.drop_constraint(
        "ck_observations_payload_consistency", "observations", type_="check"
    )
    op.create_check_constraint(
        "ck_observations_payload_consistency",
        "observations",
        "(metric_key = 'custom' AND jsonb_typeof(payload) = 'object' AND payload ? 'value' AND "
        "jsonb_typeof(payload->'value') = 'object' AND payload->'value'->>'metric' = 'custom' AND "
        "payload->'value'->>'unit' = 'custom') OR "
        "(metric_key <> 'custom' AND jsonb_typeof(payload) = 'object' AND payload ? 'value' AND "
        "jsonb_typeof(payload->'value') = 'object' AND payload->'value' ? 'metric' AND "
        "jsonb_typeof(payload->'value'->'metric') = 'string' AND payload->'value'->>'metric' = metric_key AND "
        "payload->'value' ? 'unit' AND jsonb_typeof(payload->'value'->'unit') = 'string' AND "
        "payload->'value'->>'unit' = unit AND payload->'value' ? 'value' AND "
        "jsonb_typeof(payload->'value'->'value') = 'number' AND "
        "(payload->'value'->>'value')::double precision = numeric_value)",
    )
    op.create_foreign_key(
        "fk_observations_owner_tracker",
        "observations",
        "health_objects",
        ["owner_id", "tracker_id"],
        ["owner_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_observations_tracker_shape",
        "observations",
        "(metric_key = 'custom' AND tracker_id IS NOT NULL AND tracker_schema_version IS NOT NULL AND tracker_schema_version > 0 AND "
        "jsonb_typeof(tracker_values) = 'object') OR "
        "(metric_key <> 'custom' AND tracker_id IS NULL AND tracker_schema_version IS NULL AND tracker_values IS NULL)",
    )

    op.create_table(
        "planning_resources",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("resource_kind", sa.String(length=24), nullable=False),
        sa.Column("lifecycle", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_schema_version", sa.SmallInteger(), nullable=True),
        sa.CheckConstraint(
            "resource_kind IN ('goal', 'regimen', 'plan', 'context', 'tracker_definition')",
            name="ck_planning_resources_kind",
        ),
        sa.CheckConstraint(
            "lifecycle IN ('active', 'paused', 'completed', 'ended')",
            name="ck_planning_resources_lifecycle",
        ),
        sa.CheckConstraint(
            "(resource_kind = 'goal' AND lifecycle IN ('active', 'paused', 'completed')) OR "
            "(resource_kind = 'regimen' AND lifecycle IN ('active', 'paused', 'completed')) OR "
            "(resource_kind = 'plan' AND lifecycle IN ('active', 'paused', 'completed')) OR "
            "(resource_kind = 'context' AND lifecycle IN ('active', 'ended')) OR "
            "(resource_kind = 'tracker_definition' AND lifecycle = 'active')",
            name="ck_planning_resources_kind_lifecycle",
        ),
        sa.CheckConstraint(
            "(resource_kind = 'tracker_definition' AND current_schema_version > 0) OR "
            "(resource_kind <> 'tracker_definition' AND current_schema_version IS NULL)",
            name="ck_planning_resources_tracker_version",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name="ck_planning_resources_payload"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_planning_resources_owner_object",
        ),
        sa.PrimaryKeyConstraint("owner_id", "object_id"),
    )
    op.create_index(
        "ix_planning_resources_owner_kind_lifecycle",
        "planning_resources",
        ["owner_id", "resource_kind", "lifecycle"],
    )

    op.create_table(
        "planning_links",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("parent_object_id", sa.Uuid(), nullable=False),
        sa.Column("link_id", sa.Uuid(), nullable=False),
        sa.Column("link_kind", sa.String(length=32), nullable=False),
        sa.Column("target_object_id", sa.Uuid(), nullable=True),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("priority", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("relevance", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "link_kind IN ('plan_goal', 'plan_regimen', 'plan_task', 'context_goal', 'context_regimen', 'context_profile', 'context_relation')",
            name="ck_planning_links_kind",
        ),
        sa.CheckConstraint(
            "(link_kind = 'plan_task' AND target_object_id IS NULL) OR "
            "(link_kind <> 'plan_task' AND target_object_id IS NOT NULL)",
            name="ck_planning_links_target",
        ),
        sa.CheckConstraint("position >= 0", name="ck_planning_links_position"),
        sa.CheckConstraint(
            "priority BETWEEN 0 AND 100", name="ck_planning_links_priority"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "parent_object_id"],
            ["planning_resources.owner_id", "planning_resources.object_id"],
            ondelete="CASCADE",
            name="fk_planning_links_owner_parent",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "target_object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="RESTRICT",
            name="fk_planning_links_owner_target",
        ),
        sa.PrimaryKeyConstraint("owner_id", "parent_object_id", "link_id"),
        sa.UniqueConstraint(
            "owner_id",
            "parent_object_id",
            "position",
            name="uq_planning_links_position",
        ),
    )
    op.create_index(
        "ix_planning_links_owner_target",
        "planning_links",
        ["owner_id", "target_object_id"],
    )

    op.create_table(
        "planning_schedule_identities",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("parent_object_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id", "parent_object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_planning_schedule_identity_owner_parent",
        ),
        sa.PrimaryKeyConstraint("owner_id", "schedule_id"),
        sa.ForeignKeyConstraint(
            ["owner_id", "parent_object_id", "item_id"],
            [
                "planning_links.owner_id",
                "planning_links.parent_object_id",
                "planning_links.link_id",
            ],
            ondelete="RESTRICT",
            name="fk_planning_schedule_identity_item",
        ),
        sa.UniqueConstraint(
            "owner_id",
            "parent_object_id",
            "item_id",
            name="uq_planning_schedule_identity_item",
        ),
        sa.UniqueConstraint(
            "owner_id",
            "schedule_id",
            "parent_object_id",
            name="uq_planning_schedule_identity_parent",
        ),
    )
    op.create_index(
        "uq_planning_schedule_identity_parent_without_item",
        "planning_schedule_identities",
        ["owner_id", "parent_object_id"],
        unique=True,
        postgresql_where=sa.text("item_id IS NULL"),
    )
    op.create_table(
        "planning_schedules",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.SmallInteger(), nullable=False),
        sa.Column("parent_object_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column(
            "definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("revision > 0", name="ck_planning_schedules_revision"),
        sa.CheckConstraint(
            "jsonb_typeof(definition) = 'object'",
            name="ck_planning_schedules_definition",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "schedule_id", "parent_object_id"],
            [
                "planning_schedule_identities.owner_id",
                "planning_schedule_identities.schedule_id",
                "planning_schedule_identities.parent_object_id",
            ],
            ondelete="CASCADE",
            name="fk_planning_schedules_owner_identity",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "parent_object_id", "item_id"],
            [
                "planning_links.owner_id",
                "planning_links.parent_object_id",
                "planning_links.link_id",
            ],
            ondelete="RESTRICT",
            name="fk_planning_schedules_plan_item",
        ),
        sa.PrimaryKeyConstraint("owner_id", "schedule_id", "revision"),
        sa.UniqueConstraint(
            "owner_id",
            "schedule_id",
            "effective_from",
            name="uq_planning_schedules_effective",
        ),
    )
    op.create_index(
        "ix_planning_schedules_owner_parent_effective",
        "planning_schedules",
        ["owner_id", "parent_object_id", "effective_from"],
    )
    op.create_table(
        "planning_occurrence_overrides",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("occurrence_key", sa.String(length=160), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("expected_schedule_revision", sa.SmallInteger(), nullable=False),
        sa.Column(
            "override_revision", sa.SmallInteger(), server_default="1", nullable=False
        ),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("rescheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linked_event_id", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('completed', 'skipped', 'rescheduled')",
            name="ck_occurrence_overrides_state",
        ),
        sa.CheckConstraint(
            "override_revision > 0 AND expected_schedule_revision > 0",
            name="ck_occurrence_overrides_revision",
        ),
        sa.CheckConstraint(
            "(state = 'rescheduled' AND rescheduled_at IS NOT NULL) OR "
            "(state <> 'rescheduled' AND rescheduled_at IS NULL)",
            name="ck_occurrence_overrides_rescheduled",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "schedule_id"],
            [
                "planning_schedule_identities.owner_id",
                "planning_schedule_identities.schedule_id",
            ],
            ondelete="CASCADE",
            name="fk_occurrence_overrides_owner_schedule",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "linked_event_id"],
            ["events.owner_id", "events.object_id"],
            ondelete="RESTRICT",
            name="fk_occurrence_overrides_owner_event",
        ),
        sa.PrimaryKeyConstraint("owner_id", "occurrence_key"),
    )
    op.create_index(
        "ix_occurrence_overrides_owner_schedule",
        "planning_occurrence_overrides",
        ["owner_id", "schedule_id"],
    )
    op.create_table(
        "planning_occurrence_actions",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("occurrence_key", sa.String(length=160), nullable=False),
        sa.Column("revision", sa.SmallInteger(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("schedule_revision", sa.SmallInteger(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "acted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("rescheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linked_event_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "revision > 0 AND schedule_revision > 0",
            name="ck_occurrence_actions_revision",
        ),
        sa.CheckConstraint(
            "actor_id = owner_id", name="ck_occurrence_actions_owner_actor"
        ),
        sa.CheckConstraint(
            "action IN ('completed', 'skipped', 'rescheduled')",
            name="ck_occurrence_actions_state",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "occurrence_key"],
            [
                "planning_occurrence_overrides.owner_id",
                "planning_occurrence_overrides.occurrence_key",
            ],
            ondelete="CASCADE",
            name="fk_occurrence_actions_owner_override",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_occurrence_actions_actor",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "linked_event_id"],
            ["events.owner_id", "events.object_id"],
            ondelete="RESTRICT",
            name="fk_occurrence_actions_owner_event",
        ),
        sa.PrimaryKeyConstraint("owner_id", "occurrence_key", "revision"),
    )
    op.create_table(
        "tracker_schema_versions",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("tracker_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column(
            "definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("version > 0", name="ck_tracker_schema_versions_version"),
        sa.CheckConstraint(
            "jsonb_typeof(definition) = 'object'",
            name="ck_tracker_schema_versions_definition",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "tracker_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="RESTRICT",
            name="fk_tracker_schema_versions_owner_tracker",
        ),
        sa.PrimaryKeyConstraint("owner_id", "tracker_id", "version"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    new_objects = connection.scalar(
        sa.text(
            "SELECT count(*) FROM health_objects WHERE object_type IN "
            "('goal', 'regimen', 'plan', 'context', 'tracker_definition')"
        )
    )
    custom_entries = connection.scalar(
        sa.text("SELECT count(*) FROM observations WHERE metric_key = 'custom'")
    )
    if new_objects or custom_entries:
        raise RuntimeError(
            "Phase 4 data exists; restore a compatible backup instead of downgrading"
        )

    op.drop_table("tracker_schema_versions")
    op.drop_table("planning_occurrence_actions")
    op.drop_index(
        "ix_occurrence_overrides_owner_schedule",
        table_name="planning_occurrence_overrides",
    )
    op.drop_table("planning_occurrence_overrides")
    op.drop_index(
        "ix_planning_schedules_owner_parent_effective", table_name="planning_schedules"
    )
    op.drop_table("planning_schedules")
    op.drop_index(
        "uq_planning_schedule_identity_parent_without_item",
        table_name="planning_schedule_identities",
    )
    op.drop_table("planning_schedule_identities")
    op.drop_index("ix_planning_links_owner_target", table_name="planning_links")
    op.drop_table("planning_links")
    op.drop_index(
        "ix_planning_resources_owner_kind_lifecycle", table_name="planning_resources"
    )
    op.drop_table("planning_resources")
    op.drop_constraint("ck_observations_tracker_shape", "observations", type_="check")
    op.drop_constraint(
        "fk_observations_owner_tracker", "observations", type_="foreignkey"
    )
    for name in (
        "ck_observations_payload_consistency",
        "ck_observations_numeric_value",
        "ck_observations_metric_unit",
        "ck_observations_metric",
    ):
        op.drop_constraint(name, "observations", type_="check")
    op.create_check_constraint(
        "ck_observations_metric",
        "observations",
        "metric_key IN ('weight', 'temperature', 'systolic_pressure', 'diastolic_pressure', 'pulse', 'symptom_severity')",
    )
    op.create_check_constraint(
        "ck_observations_metric_unit",
        "observations",
        "(metric_key = 'weight' AND unit IN ('kg', 'lb')) OR (metric_key = 'temperature' AND unit IN ('C', 'F')) OR "
        "(metric_key IN ('systolic_pressure', 'diastolic_pressure') AND unit = 'mmHg') OR "
        "(metric_key = 'pulse' AND unit = 'bpm') OR (metric_key = 'symptom_severity' AND unit = 'score')",
    )
    op.create_check_constraint(
        "ck_observations_numeric_value",
        "observations",
        "numeric_value > '-Infinity'::double precision AND numeric_value < 'Infinity'::double precision AND "
        "(metric_key <> 'symptom_severity' OR (numeric_value >= 0 AND numeric_value <= 10 AND numeric_value = trunc(numeric_value)))",
    )
    op.create_check_constraint(
        "ck_observations_payload_consistency",
        "observations",
        "jsonb_typeof(payload) = 'object' AND payload ? 'value' AND jsonb_typeof(payload->'value') = 'object' AND "
        "payload->'value' ? 'metric' AND jsonb_typeof(payload->'value'->'metric') = 'string' AND payload->'value'->>'metric' = metric_key AND "
        "payload->'value' ? 'unit' AND jsonb_typeof(payload->'value'->'unit') = 'string' AND payload->'value'->>'unit' = unit AND "
        "payload->'value' ? 'value' AND jsonb_typeof(payload->'value'->'value') = 'number' AND "
        "(payload->'value'->>'value')::double precision = numeric_value",
    )
    op.drop_column("observations", "tracker_values")
    op.drop_column("observations", "tracker_schema_version")
    op.drop_column("observations", "tracker_id")
    op.alter_column(
        "observations", "numeric_value", existing_type=sa.Float(), nullable=False
    )
    op.drop_constraint("ck_health_objects_domain_type", "health_objects", type_="check")
    op.drop_constraint("ck_health_objects_type", "health_objects", type_="check")
    op.create_check_constraint(
        "ck_health_objects_type",
        "health_objects",
        "object_type IN ('profile_item', 'event', 'observation')",
    )
    op.create_check_constraint(
        "ck_health_objects_domain_type",
        "health_objects",
        "(object_type = 'profile_item' AND domain = 'profile') OR "
        "(object_type = 'event' AND domain IN ('nutrition', 'exercise', 'sleep', 'symptoms')) OR "
        "(object_type = 'observation' AND domain IN ('measurements', 'symptoms'))",
    )
