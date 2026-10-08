"""Headings with their opening paragraph, and the questions a page answers.

Two rules need what a page actually says, not just how much of it there is.
3a asks whether the passage answering a query answers it first; 3b asks
which questions a page draws impressions for and does not cover. Neither
can be judged from a title, an H1 and a word count, which is all the crawl
stored.

Both columns are nullable on purpose: a crawl that predates the capture
has no sections, which is a different statement from a page with no
headings, and the rules skip rather than fire on the difference.

Revision ID: 0044_crawl_sections_and_faq
Revises: 0043_enterprise_allowance_floor
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0044_crawl_sections_and_faq"
down_revision = "0043_enterprise_allowance_floor"
branch_labels = None
depends_on = None

TABLES = ("facts_crawl_page_snapshots", "staging_crawl_pages")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for table in TABLES:
        if table not in existing:
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        if "sections" not in columns:
            op.add_column(
                table,
                sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            )
        if "faq_questions" not in columns:
            op.add_column(
                table,
                sa.Column(
                    "faq_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=True
                ),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    for table in TABLES:
        if table not in existing:
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        if "faq_questions" in columns:
            op.drop_column(table, "faq_questions")
        if "sections" in columns:
            op.drop_column(table, "sections")
