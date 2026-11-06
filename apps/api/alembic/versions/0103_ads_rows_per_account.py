"""Two Google Ads accounts of one client can have a campaign and ad group with the same names: a pulled row is unique per account too.

The three Ads tables' unique keys gain `account_id`. The old keys are dropped, which loosens what the tables accept and so cannot break the code that is
running before this lands; every row already stored satisfies the new keys.

Revision ID: 0103_ads_rows_per_account
Revises: 0102_client_ads_accounts
"""

from alembic import op

revision = "0103_ads_rows_per_account"
down_revision = "0102_client_ads_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_ads_daily_grain", "ads_daily", type_="unique")
    op.create_unique_constraint("uq_ads_daily_account_grain", "ads_daily", ["client_id", "account_id", "date", "campaign", "ad_group", "market", "device", "network"])
    op.drop_constraint("uq_ads_market_daily_grain", "ads_market_daily", type_="unique")
    op.create_unique_constraint("uq_ads_market_daily_account_grain", "ads_market_daily", ["client_id", "account_id", "date", "campaign", "market"])
    op.drop_constraint("uq_ads_search_terms_grain", "ads_search_terms", type_="unique")
    op.create_unique_constraint("uq_ads_search_terms_account_grain", "ads_search_terms", ["client_id", "account_id", "date", "term", "ad_group"])


def downgrade() -> None:
    op.drop_constraint("uq_ads_search_terms_account_grain", "ads_search_terms", type_="unique")
    op.create_unique_constraint("uq_ads_search_terms_grain", "ads_search_terms", ["client_id", "date", "term", "ad_group"])
    op.drop_constraint("uq_ads_market_daily_account_grain", "ads_market_daily", type_="unique")
    op.create_unique_constraint("uq_ads_market_daily_grain", "ads_market_daily", ["client_id", "date", "campaign", "market"])
    op.drop_constraint("uq_ads_daily_account_grain", "ads_daily", type_="unique")
    op.create_unique_constraint("uq_ads_daily_grain", "ads_daily", ["client_id", "date", "campaign", "ad_group", "market", "device", "network"])
