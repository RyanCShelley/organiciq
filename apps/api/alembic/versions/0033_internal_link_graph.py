"""Persist the internal link graph, and count editorial inbound links.

The crawler always built the graph and then threw it away, keeping only a count
per page. A count cannot answer anything about content clusters — "which of
these posts fail to link to their pillar" needs the edges and their anchors.

The count was also misleading on its own. On smamarketing.com only 12% of
inbound links are editorial; the rest is navigation, so pages sat above the
internal-linking threshold on menu links alone and were never flagged.

Revision ID: 0033_internal_link_graph
Revises: 0032_crawl_issue_source
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_internal_link_graph"
down_revision: Union[str, None] = "0032_crawl_issue_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "facts_crawl_page_snapshots",
        sa.Column(
            "inbound_editorial_links", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    op.create_table(
        "facts_crawl_internal_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        sa.Column("source", sa.String(32), nullable=False, server_default="site_crawl"),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("from_url", sa.Text(), nullable=False),
        sa.Column("to_url", sa.Text(), nullable=False),
        sa.Column("anchor_text", sa.Text(), nullable=True),
        sa.Column("in_content", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_template", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "client_id", "source", "from_url", "to_url", name="uq_facts_crawl_internal_links_grain"
        ),
    )
    op.create_index(
        "ix_facts_crawl_internal_links_client_to",
        "facts_crawl_internal_links",
        ["client_id", "to_url"],
    )
    op.create_index(
        "ix_facts_crawl_internal_links_client_from",
        "facts_crawl_internal_links",
        ["client_id", "from_url"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_facts_crawl_internal_links_client_from", table_name="facts_crawl_internal_links"
    )
    op.drop_index(
        "ix_facts_crawl_internal_links_client_to", table_name="facts_crawl_internal_links"
    )
    op.drop_table("facts_crawl_internal_links")
    op.drop_column("facts_crawl_page_snapshots", "inbound_editorial_links")
