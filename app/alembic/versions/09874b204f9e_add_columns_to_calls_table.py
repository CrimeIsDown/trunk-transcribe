"""add columns to calls table

Revision ID: 09874b204f9e
Revises: 71fea3333d68
Create Date: 2025-01-04 19:20:20.623118

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models.models import CALLS_TABLE_NAME


# revision identifiers, used by Alembic.
revision: str = "09874b204f9e"
down_revision: Union[str, None] = "71fea3333d68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(CALLS_TABLE_NAME, "raw_metadata", nullable=False)
    op.alter_column(CALLS_TABLE_NAME, "raw_audio_url", nullable=False)
    op.add_column(
        CALLS_TABLE_NAME,
        sa.Column("start_time", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        CALLS_TABLE_NAME, sa.Column("transcript_plaintext", sa.Text(), nullable=True)
    )
    op.execute(
        f"""
        UPDATE {CALLS_TABLE_NAME}
        SET transcript_plaintext = (
            SELECT string_agg(element->>1, E'\\n')
            FROM json_array_elements(raw_transcript::json) AS element
        )
        WHERE raw_transcript IS NOT NULL
        """
    )
    op.execute(
        f"""
        UPDATE {CALLS_TABLE_NAME}
        SET start_time = to_timestamp((raw_metadata->>'start_time')::bigint)
        """
    )
    op.alter_column(
        CALLS_TABLE_NAME, "start_time", server_default=sa.text("now()"), nullable=False
    )


def downgrade() -> None:
    op.drop_column(CALLS_TABLE_NAME, "transcript_plaintext")
    op.drop_column(CALLS_TABLE_NAME, "start_time")
    op.alter_column(CALLS_TABLE_NAME, "raw_audio_url", nullable=True)
    op.alter_column(CALLS_TABLE_NAME, "raw_metadata", nullable=True)
