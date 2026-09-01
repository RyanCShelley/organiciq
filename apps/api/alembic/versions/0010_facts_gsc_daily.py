"""Property-level GSC daily facts for accurate dashboard totals.

Revision ID: 0010_facts_gsc_daily
Revises: 0009_ser_ai_tracker_stats
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_facts_gsc_daily"
down_revision: Union[str, None] = "0009_ser_ai_tracker_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staging_gsc_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("impressions", sa.Numeric(), nullable=True),
        sa.Column("clicks", sa.Numeric(), nullable=True),
        sa.Column("ctr", sa.Numeric(), nullable=True),
        sa.Column("average_position", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "facts_gsc_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("ctr", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("average_position", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("client_id", "date", name="uq_facts_gsc_daily_grain"),
    )
    op.create_index("ix_facts_gsc_daily_client_date", "facts_gsc_daily", ["client_id", "date"])


def downgrade() -> None:
    op.drop_index("ix_facts_gsc_daily_client_date", table_name="facts_gsc_daily")
    op.drop_table("facts_gsc_daily")
    op.drop_table("staging_gsc_daily")
