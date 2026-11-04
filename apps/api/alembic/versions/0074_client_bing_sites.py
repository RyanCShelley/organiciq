"""Which Bing Webmaster site belongs to a client, and whether Bing confirmed it.

Revision ID: 0074_client_bing_sites
Revises: 0073_client_focus
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0074_client_bing_sites"
down_revision = "0073_client_focus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_bing_sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("site_url", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("client_bing_sites")
