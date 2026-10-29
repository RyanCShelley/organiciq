"""Competitors a client's team names.

Revision ID: 0060_client_competitors
Revises: 0059_competitor_keywords
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0060_client_competitors"
down_revision = "0059_competitor_keywords"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("competitor_domains", JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("clients", "competitor_domains")
