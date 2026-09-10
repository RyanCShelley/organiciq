"""Hot-path indexes for job claiming and staging cleanup.

claim_next_job runs every poll cycle (WHERE status='queued' ORDER BY created_at)
against a table that grows ~210 rows/day at 35 clients, and every staging fetch
and publish filters on job_id. Neither had an index.

Revision ID: 0023_job_and_staging_indexes
Revises: 0022_ser_audit_tech_signals
Create Date: 2026-09-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0023_job_and_staging_indexes"
down_revision: Union[str, None] = "0022_ser_audit_tech_signals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# staging_ser_audit_issues and staging_ser_audit_pages already carry theirs.
_STAGING_TABLES = (
    "staging_ga4_traffic",
    "staging_ga4_events",
    "staging_gsc_daily",
    "staging_gsc_pages",
    "staging_gsc_query_pages",
    "staging_ser_keywords",
    "staging_ser_positions",
    "staging_ser_competitors",
    "staging_ser_site_summary",
    "staging_ser_ai_prompts",
    "staging_ser_ai_checks",
    "staging_ser_ai_presence",
    "staging_ser_ai_tracker_stats",
)


def _index_name(table: str) -> str:
    return f"ix_{table}_job"


def upgrade() -> None:
    # IF NOT EXISTS: some of these indexes already exist in environments that
    # were built before the models declared them.
    #
    # Worker claim path: WHERE status = 'queued' ORDER BY created_at.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sync_jobs_status_created "
        "ON sync_jobs (status, created_at)"
    )
    # Client job history: WHERE client_id ORDER BY created_at DESC.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sync_jobs_client_created "
        "ON sync_jobs (client_id, created_at)"
    )

    for table in _STAGING_TABLES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {_index_name(table)} ON {table} (job_id)"
        )


def downgrade() -> None:
    for table in reversed(_STAGING_TABLES):
        op.execute(f"DROP INDEX IF EXISTS {_index_name(table)}")

    op.execute("DROP INDEX IF EXISTS ix_sync_jobs_client_created")
    op.execute("DROP INDEX IF EXISTS ix_sync_jobs_status_created")
