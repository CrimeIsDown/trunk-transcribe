"""add indexes to calls table

Revision ID: 17dc425f0a6a
Revises: 09874b204f9e
Create Date: 2025-01-04 21:49:40.293750

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "17dc425f0a6a"
down_revision: Union[str, None] = "09874b204f9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_short_name", "calls", [sa.text("(raw_metadata->>'short_name')")]
    )
    op.create_index(
        "idx_talkgroup_group", "calls", [sa.text("(raw_metadata->>'talkgroup_group')")]
    )
    op.create_index(
        "idx_talkgroup_group_tag",
        "calls",
        [sa.text("(raw_metadata->>'talkgroup_group_tag')")],
    )
    op.create_index(
        "idx_talkgroup_id", "calls", [sa.text("(raw_metadata->>'talkgroup')")]
    )
    op.create_index(
        "idx_talkgroup_tag", "calls", [sa.text("(raw_metadata->>'talkgroup_tag')")]
    )
    op.create_index("idx_start_time", "calls", ["start_time"])


def downgrade() -> None:
    op.drop_index("idx_short_name", table_name="calls")
    op.drop_index("idx_talkgroup_group", table_name="calls")
    op.drop_index("idx_talkgroup_group_tag", table_name="calls")
    op.drop_index("idx_talkgroup_id", table_name="calls")
    op.drop_index("idx_talkgroup_tag", table_name="calls")
    op.drop_index("idx_start_time", table_name="calls")
