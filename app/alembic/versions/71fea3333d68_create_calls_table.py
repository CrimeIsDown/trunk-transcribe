"""create calls table

Revision ID: 71fea3333d68
Revises:
Create Date: 2025-01-04 18:24:16.416721

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "71fea3333d68"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if the table already exists, since we are introducing migrations after the table already exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("calls"):
        # ### commands auto generated by Alembic - please adjust! ###
        op.create_table(
            "calls",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "raw_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
            ),
            sa.Column("raw_audio_url", sa.Text(), nullable=True),
            sa.Column(
                "raw_transcript", postgresql.JSONB(astext_type=sa.Text()), nullable=True
            ),
            sa.Column("geo", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
        # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("calls")
    # ### end Alembic commands ###
