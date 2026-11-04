"""Bing Webmaster query statistics, one row per query per week.

Revision ID: 0077_facts_bing_query_stats
Revises: 0076_client_business_model
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0077_facts_bing_query_stats"
down_revision = "0076_client_business_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "facts_bing_query_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False
        ),
        sa.Column("week_start", sa.Date, nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("query_key", sa.Text, nullable=False),
        sa.Column("impressions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_impression_position", sa.Numeric, nullable=True),
        sa.Column("avg_click_position", sa.Numeric, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "week_start", "query_key", name="uq_facts_bing_query_stats_grain"),
    )
    op.create_index(
        "ix_facts_bing_query_stats_client_week", "facts_bing_query_stats", ["client_id", "week_start"]
    )


def downgrade() -> None:
    op.drop_index("ix_facts_bing_query_stats_client_week", table_name="facts_bing_query_stats")
    op.drop_table("facts_bing_query_stats")
