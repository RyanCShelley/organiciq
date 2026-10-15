"""An index for one page over a window.

`facts_gsc_pages` holds 785,000 rows on SMA alone and its only usable index is
the grain, (client_id, date, normalized_url, country, device). Asking for one
page over 28 days therefore walks the date range and probes for the URL 26
times: measured at 311 ms in production. The results loop asks it for every
action, every day.

Built CONCURRENTLY so the daily sync, which writes to this table, is never
blocked while it builds. IF NOT EXISTS so a retry after a failure that left an
invalid index behind does not trip over its own name.

Revision ID: 0058_gsc_pages_url_index
Revises: 0057_brand_aliases
"""

from alembic import op

revision = "0058_gsc_pages_url_index"
down_revision = "0057_brand_aliases"
branch_labels = None
depends_on = None

INDEX = "ix_facts_gsc_pages_client_url_date"


def upgrade() -> None:
    # CONCURRENTLY cannot run inside a transaction.
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX} "
            "ON facts_gsc_pages (client_id, normalized_url, date)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}")
