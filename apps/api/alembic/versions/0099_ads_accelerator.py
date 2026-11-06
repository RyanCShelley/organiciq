"""Google Ads performance by day and search terms. Additive.

Revision ID: 0099_ads_accelerator
Revises: 0098_speed_indexes
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0099_ads_accelerator"
down_revision = "0098_speed_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ads_daily",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("campaign", sa.Text, nullable=False),
        sa.Column("ad_group", sa.Text, nullable=False, server_default=""),
        sa.Column("market", sa.Text, nullable=False, server_default=""),
        sa.Column("device", sa.String(16), nullable=False, server_default=""),
        sa.Column("network", sa.String(24), nullable=False, server_default="search"),
        sa.Column("impressions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("eligible_impressions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source", sa.String(16), nullable=False, server_default="google_ads"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "date", "campaign", "ad_group", "market", "device", "network", name="uq_ads_daily_grain"),
    )
    op.create_index("ix_ads_daily_client_date", "ads_daily", ["client_id", "date"])
    op.create_table(
        "ads_search_terms",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("term", sa.Text, nullable=False),
        sa.Column("ad_group", sa.Text, nullable=False, server_default=""),
        sa.Column("impressions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.UniqueConstraint("client_id", "date", "term", "ad_group", name="uq_ads_search_terms_grain"),
    )
    op.create_index("ix_ads_search_terms_client_date", "ads_search_terms", ["client_id", "date"])


def downgrade() -> None:
    op.drop_table("ads_search_terms")
    op.drop_table("ads_daily")
