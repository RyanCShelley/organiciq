"""Add SE Ranking AIRT tracker presence stats facts.

Revision ID: 0009_ser_ai_tracker_stats
Revises: 0008_ser_ai_presence
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_ser_ai_tracker_stats"
down_revision: Union[str, None] = "0008_ser_ai_presence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staging_ser_ai_tracker_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=True),
        sa.Column("prompts_count", sa.Integer(), nullable=True),
        sa.Column("mention_presence_pct", sa.Numeric(), nullable=True),
        sa.Column("link_presence_pct", sa.Numeric(), nullable=True),
        sa.Column("mention_top3_pct", sa.Numeric(), nullable=True),
        sa.Column("link_top3_pct", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "facts_ser_ai_tracker_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("prompts_count", sa.Integer(), nullable=True),
        sa.Column("mention_presence_pct", sa.Numeric(), nullable=True),
        sa.Column("link_presence_pct", sa.Numeric(), nullable=True),
        sa.Column("mention_top3_pct", sa.Numeric(), nullable=True),
        sa.Column("link_top3_pct", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("client_id", "metric_date", name="uq_facts_ser_ai_tracker_stats_grain"),
    )
    op.create_index(
        "ix_facts_ser_ai_tracker_stats_client_date",
        "facts_ser_ai_tracker_stats",
        ["client_id", "metric_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_facts_ser_ai_tracker_stats_client_date", table_name="facts_ser_ai_tracker_stats")
    op.drop_table("facts_ser_ai_tracker_stats")
    op.drop_table("staging_ser_ai_tracker_stats")
