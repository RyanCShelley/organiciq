"""Richer SE Ranking audit page fields + crawl issue facts.

Revision ID: 0022_ser_audit_tech_signals
Revises: 0021_gsc_secondary_properties
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_ser_audit_tech_signals"
down_revision: Union[str, None] = "0021_gsc_secondary_properties"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PAGE_COLUMNS = (
    ("title", sa.Text(), True),
    ("description", sa.Text(), True),
    ("title_duplicate", sa.Boolean(), False),
    ("description_duplicate", sa.Boolean(), False),
    ("robots", sa.Text(), True),
    ("blocked_by_robots", sa.Boolean(), False),
    ("redirect_url", sa.Text(), True),
    ("redirect_count", sa.Integer(), False),
)


def upgrade() -> None:
    for table in ("staging_ser_audit_pages", "facts_crawl_page_snapshots"):
        for name, col_type, nullable in _PAGE_COLUMNS:
            if nullable:
                op.add_column(table, sa.Column(name, col_type, nullable=True))
            elif name.endswith("_duplicate") or name == "blocked_by_robots":
                op.add_column(
                    table,
                    sa.Column(name, col_type, nullable=False, server_default=sa.text("false")),
                )
            else:
                op.add_column(
                    table,
                    sa.Column(name, col_type, nullable=False, server_default=sa.text("0")),
                )

    op.create_table(
        "staging_ser_audit_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("audit_id", sa.String(length=32), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("issue_code", sa.String(length=64), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_staging_ser_audit_issues_job", "staging_ser_audit_issues", ["job_id"])

    op.create_table(
        "facts_crawl_page_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("issue_code", sa.String(length=64), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_facts_crawl_page_issues_client", "facts_crawl_page_issues", ["client_id"])
    op.create_index(
        "ix_facts_crawl_page_issues_client_code",
        "facts_crawl_page_issues",
        ["client_id", "issue_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_facts_crawl_page_issues_client_code", table_name="facts_crawl_page_issues")
    op.drop_index("ix_facts_crawl_page_issues_client", table_name="facts_crawl_page_issues")
    op.drop_table("facts_crawl_page_issues")
    op.drop_index("ix_staging_ser_audit_issues_job", table_name="staging_ser_audit_issues")
    op.drop_table("staging_ser_audit_issues")
    for table in ("facts_crawl_page_snapshots", "staging_ser_audit_pages"):
        for name, _, _ in reversed(_PAGE_COLUMNS):
            op.drop_column(table, name)
