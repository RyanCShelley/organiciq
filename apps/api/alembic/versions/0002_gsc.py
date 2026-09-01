"""Phase 2 GSC staging + fact tables.

Revision ID: 0002_gsc
Revises: 0001_phase1
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_gsc"
down_revision: Union[str, None] = "0001_phase1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staging_gsc_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("page", sa.Text(), nullable=True),
        sa.Column("country", sa.String(16), nullable=True),
        sa.Column("device", sa.String(32), nullable=True),
        sa.Column("impressions", sa.Numeric(), nullable=True),
        sa.Column("clicks", sa.Numeric(), nullable=True),
        sa.Column("ctr", sa.Numeric(), nullable=True),
        sa.Column("average_position", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "staging_gsc_query_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("page", sa.Text(), nullable=True),
        sa.Column("country", sa.String(16), nullable=True),
        sa.Column("device", sa.String(32), nullable=True),
        sa.Column("impressions", sa.Numeric(), nullable=True),
        sa.Column("clicks", sa.Numeric(), nullable=True),
        sa.Column("ctr", sa.Numeric(), nullable=True),
        sa.Column("average_position", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "query IS NULL OR length(trim(query)) > 0",
            name="ck_staging_gsc_query_pages_query_nonblank",
        ),
    )

    op.create_table(
        "facts_gsc_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("raw_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("country", sa.String(16), nullable=False, server_default=""),
        sa.Column("device", sa.String(32), nullable=False, server_default=""),
        sa.Column("impressions", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("ctr", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("average_position", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "client_id",
            "date",
            "normalized_url",
            "country",
            "device",
            name="uq_facts_gsc_pages_grain",
        ),
    )
    op.create_index("ix_facts_gsc_pages_client_date", "facts_gsc_pages", ["client_id", "date"])

    op.create_table(
        "facts_gsc_query_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("raw_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("country", sa.String(16), nullable=False, server_default=""),
        sa.Column("device", sa.String(32), nullable=False, server_default=""),
        sa.Column("impressions", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("ctr", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("average_position", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "client_id",
            "date",
            "query",
            "normalized_url",
            "country",
            "device",
            name="uq_facts_gsc_query_pages_grain",
        ),
        sa.CheckConstraint(
            "length(trim(query)) > 0",
            name="ck_facts_gsc_query_pages_query_nonblank",
        ),
    )
    op.create_index(
        "ix_facts_gsc_query_pages_client_date",
        "facts_gsc_query_pages",
        ["client_id", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_facts_gsc_query_pages_client_date", table_name="facts_gsc_query_pages")
    op.drop_table("facts_gsc_query_pages")
    op.drop_index("ix_facts_gsc_pages_client_date", table_name="facts_gsc_pages")
    op.drop_table("facts_gsc_pages")
    op.drop_table("staging_gsc_query_pages")
    op.drop_table("staging_gsc_pages")
