"""Copilot conversations and messages.

Revision ID: 0059_copilot_conversations
Revises: 0058_gsc_pages_url_index
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0059_copilot_conversations"
down_revision = "0058_gsc_pages_url_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copilot_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("title", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_copilot_conversations_client_user", "copilot_conversations", ["client_id", "user_id"]
    )
    op.create_table(
        "copilot_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("copilot_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("tool_calls", postgresql.JSONB, nullable=True),
        sa.Column("tool_call_id", sa.String(80), nullable=True),
        sa.Column("model", sa.String(120), nullable=True),
        sa.Column("rating", sa.SmallInteger, nullable=True),
        sa.Column("correction", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_copilot_messages_conversation", "copilot_messages", ["conversation_id", "seq"]
    )


def downgrade() -> None:
    op.drop_table("copilot_messages")
    op.drop_table("copilot_conversations")
