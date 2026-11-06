"""Local Services Ads leads, one row per lead. Additive.

Revision ID: 0104_ads_lsa_leads
Revises: 0103_ads_rows_per_account
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0104_ads_lsa_leads"
down_revision = "0103_ads_rows_per_account"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ads_lsa_leads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.String(20), nullable=False, server_default=""),
        sa.Column("lead_id", sa.String(40), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("lead_type", sa.String(24), nullable=False, server_default=""),
        sa.Column("lead_status", sa.String(32), nullable=False, server_default=""),
        sa.Column("charged", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("category_id", sa.String(80), nullable=False, server_default=""),
        sa.UniqueConstraint("client_id", "account_id", "lead_id", name="uq_ads_lsa_leads_lead"),
    )
    op.create_index("ix_ads_lsa_leads_client_date", "ads_lsa_leads", ["client_id", "date"])


def downgrade() -> None:
    op.drop_table("ads_lsa_leads")
