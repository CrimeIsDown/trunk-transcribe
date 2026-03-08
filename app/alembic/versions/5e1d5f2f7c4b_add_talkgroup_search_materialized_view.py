"""add talkgroup search materialized view

Revision ID: 5e1d5f2f7c4b
Revises: 17dc425f0a6a
Create Date: 2026-03-08 15:20:00.000000

"""

from typing import Sequence, Union

from alembic import op

from app.models.models import (
    CALLS_TABLE_NAME,
    TALKGROUP_SEARCH_MATERIALIZED_VIEW_NAME,
)


# revision identifiers, used by Alembic.
revision: str = "5e1d5f2f7c4b"
down_revision: Union[str, None] = "17dc425f0a6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        f"""
        CREATE MATERIALIZED VIEW {TALKGROUP_SEARCH_MATERIALIZED_VIEW_NAME} AS
        SELECT DISTINCT
            date_trunc('hour', start_time) AS active_hour,
            raw_metadata->>'short_name' AS short_name,
            raw_metadata->>'talkgroup_group' AS talkgroup_group,
            raw_metadata->>'talkgroup_tag' AS talkgroup_tag,
            raw_metadata->>'talkgroup_description' AS talkgroup_description,
            raw_metadata->>'talkgroup' AS talkgroup,
            concat_ws(
                ' ',
                raw_metadata->>'talkgroup_group',
                raw_metadata->>'talkgroup_tag',
                raw_metadata->>'talkgroup_description',
                raw_metadata->>'talkgroup'
            ) AS search_text,
            to_tsvector(
                'simple',
                concat_ws(
                    ' ',
                    raw_metadata->>'talkgroup_group',
                    raw_metadata->>'talkgroup_tag',
                    raw_metadata->>'talkgroup_description',
                    raw_metadata->>'talkgroup'
                )
            ) AS search_vector
        FROM {CALLS_TABLE_NAME}
        WHERE
            raw_metadata->>'talkgroup_tag' != ''
            AND COALESCE(raw_metadata->>'talkgroup_description', '') != ''
        """
    )

    with op.get_context().autocommit_block():
        op.execute(
            f"""
            CREATE UNIQUE INDEX CONCURRENTLY idx_talkgroup_search_unique
            ON {TALKGROUP_SEARCH_MATERIALIZED_VIEW_NAME}
            (
                active_hour,
                short_name,
                talkgroup_group,
                talkgroup_tag,
                talkgroup_description,
                talkgroup
            )
            """
        )
        op.execute(
            f"""
            CREATE INDEX CONCURRENTLY idx_talkgroup_search_short_name_hour
            ON {TALKGROUP_SEARCH_MATERIALIZED_VIEW_NAME} (short_name, active_hour)
            """
        )
        op.execute(
            f"""
            CREATE INDEX CONCURRENTLY idx_talkgroup_search_talkgroup
            ON {TALKGROUP_SEARCH_MATERIALIZED_VIEW_NAME} (talkgroup)
            """
        )
        op.execute(
            f"""
            CREATE INDEX CONCURRENTLY idx_talkgroup_search_search_vector
            ON {TALKGROUP_SEARCH_MATERIALIZED_VIEW_NAME}
            USING gin (search_vector)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_talkgroup_search_unique")
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_talkgroup_search_short_name_hour"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_talkgroup_search_talkgroup")
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_talkgroup_search_search_vector"
        )

    op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {TALKGROUP_SEARCH_MATERIALIZED_VIEW_NAME}")
