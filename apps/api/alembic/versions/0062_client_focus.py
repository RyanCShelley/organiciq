"""The focus a client is working on in a given month.

Revision ID: 0062_client_focus
Revises: 0061_client_feeds
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0062_client_focus"
down_revision = "0061_client_feeds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_focuses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False
        ),
        sa.Column("month", sa.Date, nullable=False),
        sa.Column("focus", sa.String(16), nullable=False),
        sa.Column(
            "bucket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watchlist_buckets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "month", name="uq_client_focus_month"),
    )


def downgrade() -> None:
    op.drop_table("client_focuses")
