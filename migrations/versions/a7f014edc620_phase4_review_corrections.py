"""Preserve planning history and occurrence associations after review fixes.

Revision ID: a7f014edc620
Revises: d4e5f607a8b9
Create Date: 2026-10-05 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7f014edc620"
down_revision: str | None = "d4e5f607a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "planning_schedule_identities",
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint("ck_planning_links_kind", "planning_links", type_="check")
    op.create_check_constraint(
        "ck_planning_links_kind",
        "planning_links",
        "link_kind IN ('plan_goal', 'plan_regimen', 'plan_task', 'plan_retired', "
        "'context_goal', 'context_regimen', 'context_profile', 'context_relation')",
    )

    op.add_column(
        "planning_occurrence_overrides",
        sa.Column("original_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "planning_occurrence_overrides",
        sa.Column("original_timezone", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "planning_occurrence_overrides",
        sa.Column("dst_resolution", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "planning_occurrence_overrides",
        sa.Column("linked_observation_id", sa.Uuid(), nullable=True),
    )
    op.drop_constraint(
        "ck_occurrence_overrides_rescheduled",
        "planning_occurrence_overrides",
        type_="check",
    )
    op.create_check_constraint(
        "ck_occurrence_overrides_rescheduled",
        "planning_occurrence_overrides",
        "(state = 'rescheduled' AND rescheduled_at IS NOT NULL) OR "
        "state IN ('completed', 'skipped')",
    )
    op.create_check_constraint(
        "ck_occurrence_overrides_single_link",
        "planning_occurrence_overrides",
        "linked_event_id IS NULL OR linked_observation_id IS NULL",
    )
    op.create_foreign_key(
        "fk_occurrence_overrides_owner_observation",
        "planning_occurrence_overrides",
        "observations",
        ["owner_id", "linked_observation_id"],
        ["owner_id", "object_id"],
        ondelete="RESTRICT",
    )

    op.add_column(
        "planning_occurrence_actions",
        sa.Column("linked_observation_id", sa.Uuid(), nullable=True),
    )
    op.create_check_constraint(
        "ck_occurrence_actions_single_link",
        "planning_occurrence_actions",
        "linked_event_id IS NULL OR linked_observation_id IS NULL",
    )
    op.create_foreign_key(
        "fk_occurrence_actions_owner_observation",
        "planning_occurrence_actions",
        "observations",
        ["owner_id", "linked_observation_id"],
        ["owner_id", "object_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    connection = op.get_bind()
    review_data = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM planning_schedule_identities WHERE retired_at IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM planning_occurrence_overrides WHERE "
            "original_due_at IS NOT NULL OR original_timezone IS NOT NULL OR dst_resolution IS NOT NULL "
            "OR linked_observation_id IS NOT NULL OR "
            "(state IN ('completed', 'skipped') AND rescheduled_at IS NOT NULL)) "
            "OR EXISTS (SELECT 1 FROM planning_occurrence_actions WHERE linked_observation_id IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM planning_links WHERE link_kind = 'plan_retired')"
        )
    ).scalar_one()
    if review_data:
        raise RuntimeError(
            "refusing to downgrade recorded Phase 4 review-correction data"
        )
    op.drop_constraint(
        "fk_occurrence_actions_owner_observation",
        "planning_occurrence_actions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_occurrence_actions_single_link",
        "planning_occurrence_actions",
        type_="check",
    )
    op.drop_column("planning_occurrence_actions", "linked_observation_id")
    op.drop_constraint(
        "fk_occurrence_overrides_owner_observation",
        "planning_occurrence_overrides",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_occurrence_overrides_single_link",
        "planning_occurrence_overrides",
        type_="check",
    )
    op.drop_constraint(
        "ck_occurrence_overrides_rescheduled",
        "planning_occurrence_overrides",
        type_="check",
    )
    op.create_check_constraint(
        "ck_occurrence_overrides_rescheduled",
        "planning_occurrence_overrides",
        "(state = 'rescheduled' AND rescheduled_at IS NOT NULL) OR "
        "(state <> 'rescheduled' AND rescheduled_at IS NULL)",
    )
    op.drop_column("planning_occurrence_overrides", "linked_observation_id")
    op.drop_column("planning_occurrence_overrides", "dst_resolution")
    op.drop_column("planning_occurrence_overrides", "original_timezone")
    op.drop_column("planning_occurrence_overrides", "original_due_at")
    op.drop_constraint("ck_planning_links_kind", "planning_links", type_="check")
    op.create_check_constraint(
        "ck_planning_links_kind",
        "planning_links",
        "link_kind IN ('plan_goal', 'plan_regimen', 'plan_task', "
        "'context_goal', 'context_regimen', 'context_profile', 'context_relation')",
    )
    op.drop_column("planning_schedule_identities", "retired_at")
