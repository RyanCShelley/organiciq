"""Mark LLM responses whose prompt already names the brand.

Revision ID: 0081_llm_asked_by_name
Revises: 0080_client_llm_prompts
"""

import sqlalchemy as sa
from alembic import op

revision = "0081_llm_asked_by_name"
down_revision = "0080_client_llm_prompts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("llm_responses", sa.Column("asked_by_name", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("llm_responses", "asked_by_name")
