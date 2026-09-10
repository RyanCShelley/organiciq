"""Delete staging rows belonging to jobs that already finished.

Staging holds the raw API payload for one job and is read once, immediately
after the fetch that wrote it. Nothing ever deleted it, so every staging table
had been growing since the first sync — `staging_gsc_query_pages` worst of all
(grain: date x query x page x country x device, each row also carrying the full
JSON response).

Going forward the pipelines purge on success; this clears the backlog.

Revision ID: 0024_purge_published_staging
Revises: 0023_job_and_staging_indexes
Create Date: 2026-09-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0024_purge_published_staging"
down_revision: Union[str, None] = "0023_job_and_staging_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_STAGING_TABLES = (
    "staging_gsc_query_pages",
    "staging_gsc_pages",
    "staging_gsc_daily",
    "staging_ga4_traffic",
    "staging_ga4_events",
    "staging_ser_keywords",
    "staging_ser_positions",
    "staging_ser_competitors",
    "staging_ser_site_summary",
    "staging_ser_ai_prompts",
    "staging_ser_ai_checks",
    "staging_ser_ai_presence",
    "staging_ser_ai_tracker_stats",
    "staging_ser_audit_pages",
    "staging_ser_audit_issues",
)

# Terminal states only. Anything still queued or mid-flight keeps its rows.
_TERMINAL = "('successful', 'partial', 'failed')"


def upgrade() -> None:
    for table in _STAGING_TABLES:
        op.execute(
            f"""
            DELETE FROM {table}
            WHERE job_id IN (
                SELECT id FROM sync_jobs WHERE status::text IN {_TERMINAL}
            )
            """
        )
    # Reclaim the space rather than leaving it as bloat in the free-space map.
    for table in _STAGING_TABLES:
        op.execute(f"ANALYZE {table}")


def downgrade() -> None:
    # Deleted raw payloads cannot be reconstructed; facts are unaffected.
    pass
