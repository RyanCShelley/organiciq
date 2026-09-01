"""Add SE Ranking site summary facts for search visibility.

Revision ID: 0007_ser_site_summary
Revises: 0006_seranking_ai
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_ser_site_summary"
down_revision: Union[str, None] = "0006_seranking_ai"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staging_ser_site_summary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=True),
        sa.Column("visibility", sa.Numeric(), nullable=True),
        sa.Column("visibility_percent", sa.Numeric(), nullable=True),
        sa.Column("top5", sa.Integer(), nullable=True),
        sa.Column("top10", sa.Integer(), nullable=True),
        sa.Column("top30", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "facts_ser_site_summary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("visibility", sa.Numeric(), nullable=True),
        sa.Column("visibility_percent", sa.Numeric(), nullable=True),
        sa.Column("top5", sa.Integer(), nullable=True),
        sa.Column("top10", sa.Integer(), nullable=True),
        sa.Column("top30", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("client_id", "metric_date", name="uq_facts_ser_site_summary_grain"),
    )
    op.create_index(
        "ix_facts_ser_site_summary_client_date",
        "facts_ser_site_summary",
        ["client_id", "metric_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_facts_ser_site_summary_client_date", table_name="facts_ser_site_summary")
    op.drop_table("facts_ser_site_summary")
    op.drop_table("staging_ser_site_summary")
