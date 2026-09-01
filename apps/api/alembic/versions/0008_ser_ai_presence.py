"""Add SE Ranking AI Search overall presence facts.

Revision ID: 0008_ser_ai_presence
Revises: 0007_ser_site_summary
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_ser_ai_presence"
down_revision: Union[str, None] = "0007_ser_site_summary"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staging_ser_ai_presence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=True),
        sa.Column("source_market", sa.String(length=8), nullable=True),
        sa.Column("target_domain", sa.String(length=255), nullable=True),
        sa.Column("brand_name", sa.String(length=255), nullable=True),
        sa.Column("brand_presence_count", sa.Integer(), nullable=True),
        sa.Column("link_presence_count", sa.Integer(), nullable=True),
        sa.Column("overall_presence_pct", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "facts_ser_ai_presence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("source_market", sa.String(length=8), nullable=True),
        sa.Column("target_domain", sa.String(length=255), nullable=True),
        sa.Column("brand_name", sa.String(length=255), nullable=True),
        sa.Column("brand_presence_count", sa.Integer(), nullable=True),
        sa.Column("link_presence_count", sa.Integer(), nullable=True),
        sa.Column("overall_presence_pct", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("client_id", "metric_date", name="uq_facts_ser_ai_presence_grain"),
    )
    op.create_index(
        "ix_facts_ser_ai_presence_client_date",
        "facts_ser_ai_presence",
        ["client_id", "metric_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_facts_ser_ai_presence_client_date", table_name="facts_ser_ai_presence")
    op.drop_table("facts_ser_ai_presence")
    op.drop_table("staging_ser_ai_presence")
