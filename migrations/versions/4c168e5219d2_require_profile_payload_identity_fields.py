"""require profile payload identity fields

Revision ID: 4c168e5219d2
Revises: 22dad79c2ee1
Create Date: 2026-10-03 19:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c168e5219d2"
down_revision: str | None = "22dad79c2ee1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_profile_items_payload_consistency", "profile_items", type_="check"
    )
    op.create_check_constraint(
        "ck_profile_items_payload_consistency",
        "profile_items",
        "jsonb_typeof(payload) = 'object' AND "
        "payload ? 'kind' AND jsonb_typeof(payload->'kind') = 'string' AND "
        "payload->>'kind' = kind AND payload ? 'category' AND "
        "jsonb_typeof(payload->'category') = 'string' AND "
        "payload->>'category' = category AND payload ? 'key' AND "
        "jsonb_typeof(payload->'key') = 'string' AND payload->>'key' = key",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_profile_items_payload_consistency", "profile_items", type_="check"
    )
    op.create_check_constraint(
        "ck_profile_items_payload_consistency",
        "profile_items",
        "jsonb_typeof(payload) = 'object' AND payload->>'kind' = kind AND "
        "payload->>'category' = category AND payload->>'key' = key",
    )
