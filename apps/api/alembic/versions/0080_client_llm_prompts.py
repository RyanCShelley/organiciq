"""Prompts a client's LLM visibility runs ask beyond the watchlist's paired prompts.

Revision ID: 0080_client_llm_prompts
Revises: 0079_llm_visibility
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0080_client_llm_prompts"
down_revision = "0079_llm_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_llm_prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("prompt_key", sa.String(600), nullable=False),
        sa.Column("topic_cluster", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "prompt_key", name="uq_client_llm_prompt"),
    )


def downgrade() -> None:
    op.drop_table("client_llm_prompts")
