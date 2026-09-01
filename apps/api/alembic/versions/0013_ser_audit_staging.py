"""SE Ranking Website Audit staging table.

Revision ID: 0013_ser_audit_staging
Revises: 0012_lever_engine
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_ser_audit_staging"
down_revision: Union[str, None] = "0012_lever_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staging_ser_audit_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("audit_id", sa.String(length=32), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("raw_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("indexable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("inbound_internal_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("in_sitemap", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_staging_ser_audit_pages_job",
        "staging_ser_audit_pages",
        ["job_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_staging_ser_audit_pages_job", table_name="staging_ser_audit_pages")
    op.drop_table("staging_ser_audit_pages")
