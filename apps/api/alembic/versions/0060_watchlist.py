"""Watchlist buckets and keywords.

Revision ID: 0060_watchlist
Revises: 0059_copilot_conversations
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0060_watchlist"
down_revision = "0059_copilot_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_buckets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("name_key", sa.String(160), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "name_key", name="uq_watchlist_bucket_name"),
    )
    op.create_table(
        "watchlist_keywords",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False
        ),
        sa.Column(
            "bucket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watchlist_buckets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("keyword", sa.String(400), nullable=False),
        sa.Column("keyword_key", sa.String(400), nullable=False),
        sa.Column("volume", sa.Integer, nullable=True),
        sa.Column("difficulty", sa.Integer, nullable=True),
        sa.Column("intent", sa.String(120), nullable=True),
        sa.Column("paired_ai_prompt", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("source", sa.String(24), nullable=False, server_default="csv"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "keyword_key", name="uq_watchlist_keyword"),
    )
    op.create_index("ix_watchlist_keywords_bucket", "watchlist_keywords", ["bucket_id"])


def downgrade() -> None:
    op.drop_index("ix_watchlist_keywords_bucket", table_name="watchlist_keywords")
    op.drop_table("watchlist_keywords")
    op.drop_table("watchlist_buckets")
