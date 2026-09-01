"""Crawl snapshots and decision scoring columns.

Revision ID: 0012_lever_engine
Revises: 0011_decisions
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_lever_engine"
down_revision: Union[str, None] = "0011_decisions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "facts_crawl_page_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("raw_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("indexable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("inbound_internal_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("in_sitemap", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("client_id", "normalized_url", name="uq_facts_crawl_page_snapshots_grain"),
    )
    op.create_index(
        "ix_facts_crawl_page_snapshots_client",
        "facts_crawl_page_snapshots",
        ["client_id"],
    )

    op.add_column("decisions", sa.Column("priority_score", sa.Numeric(), nullable=True))
    op.add_column("decisions", sa.Column("impact", sa.Numeric(), nullable=True))
    op.add_column("decisions", sa.Column("confidence", sa.Numeric(), nullable=True))
    op.add_column("decisions", sa.Column("urgency", sa.Numeric(), nullable=True))
    op.add_column("decisions", sa.Column("effort", sa.Numeric(), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "effort")
    op.drop_column("decisions", "urgency")
    op.drop_column("decisions", "confidence")
    op.drop_column("decisions", "impact")
    op.drop_column("decisions", "priority_score")
    op.drop_index("ix_facts_crawl_page_snapshots_client", table_name="facts_crawl_page_snapshots")
    op.drop_table("facts_crawl_page_snapshots")
