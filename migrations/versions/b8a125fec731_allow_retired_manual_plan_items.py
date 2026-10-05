"""Allow retained scheduled manual tasks to have no reference target.

Revision ID: b8a125fec731
Revises: a7f014edc620
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8a125fec731"
down_revision: str | None = "a7f014edc620"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_planning_links_target", "planning_links", type_="check")
    op.create_check_constraint(
        "ck_planning_links_target",
        "planning_links",
        "link_kind = 'plan_retired' OR "
        "(link_kind = 'plan_task' AND target_object_id IS NULL) OR "
        "(link_kind NOT IN ('plan_task', 'plan_retired') AND target_object_id IS NOT NULL)",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM planning_links "
            "WHERE link_kind = 'plan_retired' AND target_object_id IS NULL)"
        )
    ):
        raise RuntimeError("refusing to downgrade retained scheduled manual tasks")
    op.drop_constraint("ck_planning_links_target", "planning_links", type_="check")
    op.create_check_constraint(
        "ck_planning_links_target",
        "planning_links",
        "(link_kind = 'plan_task' AND target_object_id IS NULL) OR "
        "(link_kind <> 'plan_task' AND target_object_id IS NOT NULL)",
    )
