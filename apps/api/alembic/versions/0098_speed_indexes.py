"""Two indexes for the CTR optimizer and the Inlink suggester, built without blocking writes. Additive.

Revision ID: 0098_speed_indexes
Revises: 0097_teamwork_subtasks
"""

from alembic import op

revision = "0098_speed_indexes"
down_revision = "0097_teamwork_subtasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_facts_gsc_query_pages_client_url_date ON facts_gsc_query_pages (client_id, normalized_url, date)")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_facts_crawl_page_snapshots_client_date ON facts_crawl_page_snapshots (client_id, snapshot_date)")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_facts_crawl_page_snapshots_client_date")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_facts_gsc_query_pages_client_url_date")
