"""First-party site crawl: a source column on page snapshots, and structured data.

The crawl source becomes part of the snapshot grain so our own crawler and SE
Ranking's Website Audit can both write for the same client and be compared.
Nothing reads the new source yet — the Technical lever keeps reading the audit
until the parallel run says the two agree.

Existing rows are the SE Ranking audit by definition, so they backfill to that.

Revision ID: 0030_first_party_crawl
Revises: 0029_client_ai_search_limit
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_first_party_crawl"
down_revision: Union[str, None] = "0029_client_ai_search_limit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "facts_crawl_page_snapshots",
        sa.Column(
            "source",
            sa.String(32),
            nullable=False,
            server_default="se_ranking_audit",
        ),
    )
    # The grain gains the source, so both crawlers can hold a row per page.
    op.drop_constraint(
        "uq_facts_crawl_page_snapshots_grain",
        "facts_crawl_page_snapshots",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_facts_crawl_page_snapshots_grain",
        "facts_crawl_page_snapshots",
        ["client_id", "source", "normalized_url"],
    )
    op.create_index(
        "ix_facts_crawl_page_snapshots_client_source",
        "facts_crawl_page_snapshots",
        ["client_id", "source"],
    )

    op.create_table(
        "facts_crawl_page_schema",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("syntax", sa.String(16), nullable=False),
        sa.Column("schema_type", sa.String(128), nullable=True),
        sa.Column("raw", postgresql.JSONB(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_facts_crawl_page_schema_client", "facts_crawl_page_schema", ["client_id"]
    )
    op.create_index(
        "ix_facts_crawl_page_schema_client_url",
        "facts_crawl_page_schema",
        ["client_id", "normalized_url"],
    )
    op.create_index(
        "ix_facts_crawl_page_schema_client_type",
        "facts_crawl_page_schema",
        ["client_id", "schema_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_facts_crawl_page_schema_client_type", table_name="facts_crawl_page_schema")
    op.drop_index("ix_facts_crawl_page_schema_client_url", table_name="facts_crawl_page_schema")
    op.drop_index("ix_facts_crawl_page_schema_client", table_name="facts_crawl_page_schema")
    op.drop_table("facts_crawl_page_schema")

    # Drop first-party rows before narrowing the grain, or the constraint fails.
    op.execute("DELETE FROM facts_crawl_page_snapshots WHERE source <> 'se_ranking_audit'")
    op.drop_index(
        "ix_facts_crawl_page_snapshots_client_source", table_name="facts_crawl_page_snapshots"
    )
    op.drop_constraint(
        "uq_facts_crawl_page_snapshots_grain",
        "facts_crawl_page_snapshots",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_facts_crawl_page_snapshots_grain",
        "facts_crawl_page_snapshots",
        ["client_id", "normalized_url"],
    )
    op.drop_column("facts_crawl_page_snapshots", "source")
