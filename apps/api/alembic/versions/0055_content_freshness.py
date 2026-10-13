"""When a page was last updated, and which source said so.

A refresh programme ranks on what a page is losing and how long since
anybody touched it, and the second half was not recorded anywhere. The
crawler reads the HTML already: `parse_page` queried `meta` by `@name`
only, so `article:modified_time` was never seen, and the sitemap loop read
`<loc>` and stepped past `<lastmod>`.

Nullable on purpose. Null is "no source on this page carried a date", which
is not "never updated" — a queue that treated a missing date as ancient
would put every page without markup at the top.

The HTTP `Last-Modified` header is deliberately not one of the sources.
ACCTek's /managed-it-services-syracuse-ny returns 11 October while its own
`article:modified_time` says 16 May: the header is a cache artifact and
would report every page as fresh.

Revision ID: 0055_content_freshness
Revises: 0054_keyword_page_suggestions
"""

from alembic import op
import sqlalchemy as sa

revision = "0055_content_freshness"
down_revision = "0054_keyword_page_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "facts_crawl_page_snapshots",
        sa.Column("content_updated_on", sa.Date(), nullable=True),
    )
    op.add_column(
        "facts_crawl_page_snapshots",
        sa.Column("content_updated_source", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("facts_crawl_page_snapshots", "content_updated_source")
    op.drop_column("facts_crawl_page_snapshots", "content_updated_on")
