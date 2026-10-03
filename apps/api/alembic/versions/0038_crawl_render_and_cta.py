"""Soft 404s, robots-blocked render resources, and conversion elements.

Three things the crawler can see and was throwing away. A page that says
404 while returning 200, a page whose CSS or JS robots.txt forbids, and a
page with nothing on it to convert through.

Revision ID: 0038_crawl_render_and_cta
Revises: 0037_ser_backlink_pages
"""

from alembic import op
import sqlalchemy as sa

revision = "0038_crawl_render_and_cta"
down_revision = "0037_ser_backlink_pages"
branch_labels = None
depends_on = None

TABLE = "facts_crawl_page_snapshots"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("soft_404", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "blocked_resources", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    # Nullable, with no default: a crawl that ran before this check counted
    # nothing, and recording that as zero would read as "this page has no way
    # to convert" on every page crawled so far.
    op.add_column(TABLE, sa.Column("conversion_elements", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column(TABLE, "conversion_elements")
    op.drop_column(TABLE, "blocked_resources")
    op.drop_column(TABLE, "soft_404")
