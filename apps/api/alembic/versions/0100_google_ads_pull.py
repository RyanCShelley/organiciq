"""The Google Ads account a client is, how its last pull went, and a table for markets (Google reports them apart from ad groups and devices). Additive.

Revision ID: 0100_google_ads_pull
Revises: 0099_ads_accelerator
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0100_google_ads_pull"
down_revision = "0099_ads_accelerator"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("google_ads_customer_id", sa.String(20), nullable=True))
    op.add_column("clients", sa.Column("google_ads_last_pull_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("clients", sa.Column("google_ads_last_error", sa.Text, nullable=True))
    op.create_table(
        "ads_market_daily",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("campaign", sa.Text, nullable=False),
        sa.Column("market", sa.Text, nullable=False),
        sa.Column("impressions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("source", sa.String(16), nullable=False, server_default="google_ads"),
        sa.UniqueConstraint("client_id", "date", "campaign", "market", name="uq_ads_market_daily_grain"),
    )
    op.create_index("ix_ads_market_daily_client_date", "ads_market_daily", ["client_id", "date"])
    op.add_column("ads_search_terms", sa.Column("source", sa.String(16), nullable=False, server_default="google_ads"))


def downgrade() -> None:
    op.drop_column("ads_search_terms", "source")
    op.drop_table("ads_market_daily")
    op.drop_column("clients", "google_ads_last_error")
    op.drop_column("clients", "google_ads_last_pull_at")
    op.drop_column("clients", "google_ads_customer_id")
