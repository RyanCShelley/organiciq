"""A client's blog or news feeds, polled to learn what was published and when.

Revision ID: 0072_client_feeds
Revises: 0071_watchlist
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0072_client_feeds"
down_revision = "0071_watchlist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_feeds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False
        ),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("url_key", sa.Text, nullable=False),
        sa.Column("label", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "url_key", name="uq_client_feed_url"),
    )
    op.create_index("ix_client_feeds_client", "client_feeds", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_client_feeds_client", table_name="client_feeds")
    op.drop_table("client_feeds")
