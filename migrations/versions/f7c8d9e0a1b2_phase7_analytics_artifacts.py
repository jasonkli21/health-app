"""Persist versioned Phase 7 analytics and experiments in canonical history."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7c8d9e0a1b2"
down_revision: str | Sequence[str] | None = "20261006b1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_health_objects_type", "health_objects", type_="check")
    op.drop_constraint("ck_health_objects_domain_type", "health_objects", type_="check")
    op.create_check_constraint(
        "ck_health_objects_type",
        "health_objects",
        "object_type IN ('profile_item', 'event', 'observation', 'goal', 'regimen', 'plan', "
        "'context', 'tracker_definition', 'derived_signal', 'insight', 'recommendation', 'experiment')",
    )
    op.create_check_constraint(
        "ck_health_objects_domain_type",
        "health_objects",
        "(object_type = 'profile_item' AND domain = 'profile') OR "
        "(object_type = 'event' AND domain IN ('nutrition', 'exercise', 'sleep', 'symptoms')) OR "
        "(object_type = 'observation' AND domain IN ('measurements', 'symptoms', 'nutrition', 'exercise', 'sleep')) OR "
        "(object_type IN ('goal', 'regimen', 'plan', 'context', 'tracker_definition') AND domain IN "
        "('planning', 'nutrition', 'exercise', 'sleep', 'symptoms', 'measurements', 'general')) OR "
        "(object_type IN ('derived_signal', 'insight', 'recommendation', 'experiment') AND domain = 'analytics')",
    )
    op.create_table(
        "analytics_artifacts",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_kind", sa.String(length=24), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("scope_key", sa.String(length=128), nullable=True),
        sa.Column("dedupe_key", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False),
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
        sa.CheckConstraint(
            "artifact_kind IN ('derived_signal', 'insight', 'recommendation', 'experiment')",
            name="ck_analytics_artifacts_kind",
        ),
        sa.CheckConstraint(
            "(artifact_kind = 'derived_signal' AND state IN ('current', 'stale')) OR "
            "(artifact_kind = 'insight' AND state IN ('current', 'stale', 'dismissed', 'expired')) OR "
            "(artifact_kind = 'recommendation' AND state IN ('proposed', 'accepted', 'dismissed', 'expired', 'stale')) OR "
            "(artifact_kind = 'experiment' AND state IN ('draft', 'active', 'completed', 'stopped', 'archived'))",
            name="ck_analytics_artifacts_state",
        ),
        sa.CheckConstraint(
            "dedupe_key IS NULL OR length(dedupe_key) = 64",
            name="ck_analytics_artifacts_dedupe_key",
        ),
        sa.CheckConstraint(
            "artifact_kind = 'derived_signal' OR scope_key IS NULL",
            name="ck_analytics_artifacts_scope_key",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "object_id"],
            ["health_objects.owner_id", "health_objects.id"],
            ondelete="CASCADE",
            name="fk_analytics_artifacts_owner_object",
        ),
        sa.PrimaryKeyConstraint("owner_id", "object_id"),
        sa.UniqueConstraint(
            "owner_id",
            "artifact_kind",
            "dedupe_key",
            name="uq_analytics_artifacts_dedupe",
        ),
    )
    op.create_index(
        "ix_analytics_artifacts_owner_kind_state_updated",
        "analytics_artifacts",
        ["owner_id", "artifact_kind", "state", "updated_at", "object_id"],
    )
    op.create_index(
        "ix_analytics_artifacts_owner_kind_scope_state",
        "analytics_artifacts",
        ["owner_id", "artifact_kind", "scope_key", "state"],
    )
    op.create_table(
        "analytics_evidence",
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_object_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_object_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_revision", sa.Integer(), nullable=False),
        sa.Column("evidence_object_type", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "evidence_revision > 0", name="ck_analytics_evidence_revision"
        ),
        sa.CheckConstraint(
            "evidence_object_type IN ('derived_signal', 'event', 'observation')",
            name="ck_analytics_evidence_object_type",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "artifact_object_id"],
            ["analytics_artifacts.owner_id", "analytics_artifacts.object_id"],
            ondelete="CASCADE",
            name="fk_analytics_evidence_artifact",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "evidence_object_id", "evidence_revision"],
            [
                "health_object_revisions.owner_id",
                "health_object_revisions.object_id",
                "health_object_revisions.revision",
            ],
            ondelete="RESTRICT",
            name="fk_analytics_evidence_revision",
        ),
        sa.PrimaryKeyConstraint(
            "owner_id", "artifact_object_id", "evidence_object_id", "evidence_revision"
        ),
    )
    op.create_index(
        "ix_analytics_evidence_owner_source",
        "analytics_evidence",
        ["owner_id", "evidence_object_id", "evidence_revision"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    existing_artifacts = connection.scalar(
        sa.text("SELECT 1 FROM analytics_artifacts LIMIT 1")
    )
    if existing_artifacts:
        raise RuntimeError(
            "refusing to discard Phase 7 analytical history during downgrade"
        )
    op.drop_index("ix_analytics_evidence_owner_source", table_name="analytics_evidence")
    op.drop_table("analytics_evidence")
    op.drop_index(
        "ix_analytics_artifacts_owner_kind_scope_state",
        table_name="analytics_artifacts",
    )
    op.drop_index(
        "ix_analytics_artifacts_owner_kind_state_updated",
        table_name="analytics_artifacts",
    )
    op.drop_table("analytics_artifacts")
    op.drop_constraint("ck_health_objects_domain_type", "health_objects", type_="check")
    op.drop_constraint("ck_health_objects_type", "health_objects", type_="check")
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
