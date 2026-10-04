"""add owner-scoped daily event and observation storage

Revision ID: 8e31c7c9a0b2
Revises: 4c168e5219d2
Create Date: 2026-10-03 23:55:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8e31c7c9a0b2"
down_revision: str | None = "4c168e5219d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("daily_sequence", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_users_daily_sequence", "users", "daily_sequence >= 0"
    )

    op.drop_constraint("ck_health_objects_type_phase1", "health_objects", type_="check")
    op.drop_constraint(
        "ck_health_objects_domain_phase1", "health_objects", type_="check"
    )
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

    op.add_column("health_object_revisions", sa.Column("daily_sequence", sa.Integer()))
    op.add_column(
        "health_object_revisions", sa.Column("daily_object_type", sa.String(length=16))
    )
    op.add_column(
        "health_object_revisions", sa.Column("daily_domain", sa.String(length=24))
    )
    op.add_column(
        "health_object_revisions", sa.Column("daily_status", sa.String(length=16))
    )
    op.add_column(
        "health_object_revisions",
        sa.Column("daily_time_precision", sa.String(length=16)),
    )
    op.add_column(
        "health_object_revisions",
        sa.Column("daily_occurred_at", sa.DateTime(timezone=True)),
    )
    op.add_column("health_object_revisions", sa.Column("daily_local_date", sa.Date()))
    op.add_column(
        "health_object_revisions",
        sa.Column("daily_ended_at", sa.DateTime(timezone=True)),
    )
    op.create_check_constraint(
        "ck_health_object_revisions_daily_snapshot_shape",
        "health_object_revisions",
        "(daily_sequence IS NULL AND daily_object_type IS NULL AND daily_domain IS NULL AND "
        "daily_status IS NULL AND daily_time_precision IS NULL AND daily_occurred_at IS NULL AND "
        "daily_local_date IS NULL AND daily_ended_at IS NULL) OR "
        "(daily_sequence > 0 AND daily_object_type IN ('event', 'observation') AND "
        "daily_domain IN ('nutrition', 'exercise', 'sleep', 'symptoms', 'measurements') AND "
        "daily_status IN ('active', 'archived') AND "
        "((daily_time_precision = 'instant' AND daily_occurred_at IS NOT NULL AND "
        "daily_local_date IS NULL) OR (daily_time_precision = 'date_only' AND "
        "daily_occurred_at IS NULL AND daily_local_date IS NOT NULL AND daily_ended_at IS NULL)))",
    )
    op.create_unique_constraint(
        "uq_health_object_revision_daily_sequence",
        "health_object_revisions",
        ["owner_id", "daily_sequence"],
    )
    op.create_index(
        "ix_health_revisions_owner_daily_instant",
        "health_object_revisions",
        [
            "owner_id",
            "daily_domain",
            "daily_occurred_at",
            "object_id",
            "daily_sequence",
        ],
    )
    op.create_index(
        "ix_health_revisions_owner_daily_date",
        "health_object_revisions",
        ["owner_id", "daily_domain", "daily_local_date", "object_id", "daily_sequence"],
    )
    op.create_index(
        "ix_health_revisions_owner_object_daily_sequence",
        "health_object_revisions",
        ["owner_id", "object_id", "daily_sequence"],
    )

    op.create_table(
        "events",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("event_kind", sa.String(length=16), nullable=False),
        sa.Column("time_precision", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("local_date", sa.Date(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "event_kind IN ('meal', 'workout', 'sleep', 'symptom')",
            name="ck_events_kind",
        ),
        sa.CheckConstraint(
            "(time_precision = 'instant' AND occurred_at IS NOT NULL AND local_date IS NULL) OR "
            "(time_precision = 'date_only' AND occurred_at IS NULL AND local_date IS NOT NULL AND ended_at IS NULL)",
            name="ck_events_time_precision_shape",
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR (occurred_at IS NOT NULL AND occurred_at < ended_at)",
            name="ck_events_interval",
        ),
        sa.CheckConstraint(
            "char_length(timezone) BETWEEN 1 AND 64", name="ck_events_timezone_length"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND payload ? 'kind' AND "
            "jsonb_typeof(payload->'kind') = 'string' AND payload->>'kind' = event_kind",
            name="ck_events_payload_kind",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_events_owner_object",
        ),
        sa.PrimaryKeyConstraint("owner_id", "object_id"),
    )
    op.create_index(
        "ix_events_owner_instant", "events", ["owner_id", "occurred_at", "object_id"]
    )
    op.create_index(
        "ix_events_owner_date", "events", ["owner_id", "local_date", "object_id"]
    )

    op.create_table(
        "observations",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("metric_key", sa.String(length=32), nullable=False),
        sa.Column("time_precision", sa.String(length=16), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("local_date", sa.Date(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("numeric_value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "metric_key IN ('weight', 'temperature', 'systolic_pressure', "
            "'diastolic_pressure', 'pulse', 'symptom_severity')",
            name="ck_observations_metric",
        ),
        sa.CheckConstraint(
            "(metric_key = 'weight' AND unit IN ('kg', 'lb')) OR "
            "(metric_key = 'temperature' AND unit IN ('C', 'F')) OR "
            "(metric_key IN ('systolic_pressure', 'diastolic_pressure') AND unit = 'mmHg') OR "
            "(metric_key = 'pulse' AND unit = 'bpm') OR "
            "(metric_key = 'symptom_severity' AND unit = 'score')",
            name="ck_observations_metric_unit",
        ),
        sa.CheckConstraint(
            "numeric_value > '-Infinity'::double precision AND "
            "numeric_value < 'Infinity'::double precision AND "
            "(metric_key <> 'symptom_severity' OR "
            "(numeric_value >= 0 AND numeric_value <= 10 AND numeric_value = trunc(numeric_value)))",
            name="ck_observations_numeric_value",
        ),
        sa.CheckConstraint(
            "(time_precision = 'instant' AND observed_at IS NOT NULL AND local_date IS NULL) OR "
            "(time_precision = 'date_only' AND observed_at IS NULL AND local_date IS NOT NULL AND interval_end IS NULL)",
            name="ck_observations_time_precision_shape",
        ),
        sa.CheckConstraint(
            "interval_end IS NULL OR (observed_at IS NOT NULL AND observed_at < interval_end)",
            name="ck_observations_interval",
        ),
        sa.CheckConstraint(
            "char_length(timezone) BETWEEN 1 AND 64",
            name="ck_observations_timezone_length",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND payload ? 'value' AND "
            "jsonb_typeof(payload->'value') = 'object' AND payload->'value' ? 'metric' AND "
            "jsonb_typeof(payload->'value'->'metric') = 'string' AND "
            "payload->'value'->>'metric' = metric_key AND payload->'value' ? 'unit' AND "
            "jsonb_typeof(payload->'value'->'unit') = 'string' AND "
            "payload->'value'->>'unit' = unit AND payload->'value' ? 'value' AND "
            "jsonb_typeof(payload->'value'->'value') = 'number' AND "
            "(payload->'value'->>'value')::double precision = numeric_value",
            name="ck_observations_payload_consistency",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_observations_owner_object",
        ),
        sa.PrimaryKeyConstraint("owner_id", "object_id"),
    )
    op.create_index(
        "ix_observations_owner_metric_instant",
        "observations",
        ["owner_id", "metric_key", "observed_at", "object_id"],
    )
    op.create_index(
        "ix_observations_owner_metric_date",
        "observations",
        ["owner_id", "metric_key", "local_date", "object_id"],
    )

    op.create_table(
        "event_observation_links",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("event_object_id", sa.Uuid(), nullable=False),
        sa.Column("observation_object_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "role = 'symptom_severity'", name="ck_event_observation_links_role"
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "event_object_id"],
            ["events.owner_id", "events.object_id"],
            ondelete="CASCADE",
            name="fk_event_observation_links_owner_event",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "observation_object_id"],
            ["observations.owner_id", "observations.object_id"],
            ondelete="CASCADE",
            name="fk_event_observation_links_owner_observation",
        ),
        sa.PrimaryKeyConstraint("owner_id", "event_object_id", "observation_object_id"),
        sa.UniqueConstraint(
            "owner_id", "event_object_id", "role", name="uq_event_observation_link_role"
        ),
        sa.UniqueConstraint(
            "owner_id",
            "observation_object_id",
            "role",
            name="uq_observation_event_link_role",
        ),
    )
    op.create_index(
        "ix_event_observation_links_owner_observation",
        "event_observation_links",
        ["owner_id", "observation_object_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    daily_count = connection.scalar(
        sa.text(
            "SELECT count(*) FROM health_objects WHERE object_type IN ('event', 'observation')"
        )
    )
    if daily_count:
        raise RuntimeError("refusing to downgrade while daily health objects exist")

    op.drop_index(
        "ix_event_observation_links_owner_observation",
        table_name="event_observation_links",
    )
    op.drop_table("event_observation_links")
    op.drop_index("ix_observations_owner_metric_date", table_name="observations")
    op.drop_index("ix_observations_owner_metric_instant", table_name="observations")
    op.drop_table("observations")
    op.drop_index("ix_events_owner_date", table_name="events")
    op.drop_index("ix_events_owner_instant", table_name="events")
    op.drop_table("events")

    op.drop_index(
        "ix_health_revisions_owner_object_daily_sequence",
        table_name="health_object_revisions",
    )
    op.drop_index(
        "ix_health_revisions_owner_daily_date", table_name="health_object_revisions"
    )
    op.drop_index(
        "ix_health_revisions_owner_daily_instant", table_name="health_object_revisions"
    )
    op.drop_constraint(
        "uq_health_object_revision_daily_sequence",
        "health_object_revisions",
        type_="unique",
    )
    op.drop_constraint(
        "ck_health_object_revisions_daily_snapshot_shape",
        "health_object_revisions",
        type_="check",
    )
    op.drop_column("health_object_revisions", "daily_ended_at")
    op.drop_column("health_object_revisions", "daily_local_date")
    op.drop_column("health_object_revisions", "daily_occurred_at")
    op.drop_column("health_object_revisions", "daily_time_precision")
    op.drop_column("health_object_revisions", "daily_status")
    op.drop_column("health_object_revisions", "daily_domain")
    op.drop_column("health_object_revisions", "daily_object_type")
    op.drop_column("health_object_revisions", "daily_sequence")

    op.drop_constraint("ck_health_objects_domain_type", "health_objects", type_="check")
    op.drop_constraint("ck_health_objects_type", "health_objects", type_="check")
    op.create_check_constraint(
        "ck_health_objects_domain_phase1", "health_objects", "domain = 'profile'"
    )
    op.create_check_constraint(
        "ck_health_objects_type_phase1",
        "health_objects",
        "object_type = 'profile_item'",
    )
    op.drop_constraint("ck_users_daily_sequence", "users", type_="check")
    op.drop_column("users", "daily_sequence")
