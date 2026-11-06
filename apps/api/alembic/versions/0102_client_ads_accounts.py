"""A client can have several Google Ads accounts (search ads, Local Services Ads), and each pulled row says which one it came from. Additive.

The one account a client could have (`clients.google_ads_customer_id`) is copied into the new table; the old columns stay unused.

Revision ID: 0102_client_ads_accounts
Revises: 0101_lead_exclusions
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0102_client_ads_accounts"
down_revision = "0101_lead_exclusions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_ads_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("kind", sa.String(8), nullable=False, server_default="ads"),
        sa.Column("last_pull_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "customer_id", name="uq_client_ads_account"),
    )
    for table in ("ads_daily", "ads_market_daily", "ads_search_terms"):
        op.add_column(table, sa.Column("account_id", sa.String(20), nullable=False, server_default=""))
    op.execute(
        "INSERT INTO client_ads_accounts (id, client_id, customer_id, last_pull_at, last_error) "
        "SELECT gen_random_uuid(), id, google_ads_customer_id, google_ads_last_pull_at, google_ads_last_error FROM clients WHERE google_ads_customer_id IS NOT NULL"
    )


def downgrade() -> None:
    for table in ("ads_search_terms", "ads_market_daily", "ads_daily"):
        op.drop_column(table, "account_id")
    op.drop_table("client_ads_accounts")
