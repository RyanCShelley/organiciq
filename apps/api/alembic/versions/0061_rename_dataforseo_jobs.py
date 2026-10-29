"""Name the two DataForSEO jobs for what they read.

They were queued as `se_ranking_keyword_metrics` and
`se_ranking_competitor_keywords` after they moved to DataForSEO, which made the
jobs page say SE Ranking for work SE Ranking no longer does. History is renamed
with them so one job has one name; a job still waiting under an old name is
handled by the aliases in `services.jobs`.

Revision ID: 0061_rename_dataforseo_jobs
Revises: 0060_client_competitors
"""

from alembic import op

revision = "0061_rename_dataforseo_jobs"
down_revision = "0060_client_competitors"
branch_labels = None
depends_on = None

RENAMES = (
    ("se_ranking_keyword_metrics", "dataforseo_keyword_metrics"),
    ("se_ranking_competitor_keywords", "dataforseo_competitor_keywords"),
)


def upgrade() -> None:
    for old, new in RENAMES:
        # Not while one is queued or running: the one-active-job-per-source
        # index would see the new name and the old at once.
        op.execute(
            f"UPDATE sync_jobs SET source = '{new}' WHERE source = '{old}' "
            "AND status IN ('successful', 'partial', 'failed')"
        )


def downgrade() -> None:
    for old, new in RENAMES:
        op.execute(
            f"UPDATE sync_jobs SET source = '{old}' WHERE source = '{new}' "
            "AND status IN ('successful', 'partial', 'failed')"
        )
