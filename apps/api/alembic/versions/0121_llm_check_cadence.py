"""Add check_cadence to client_llm_settings for daily/weekly/monthly LLM checks.

Revision ID: 0121_llm_check_cadence
Revises: 0120_serp_ai_overview_and_mode
"""

from alembic import op
import sqlalchemy as sa

revision = "0121_llm_check_cadence"
down_revision = "0120_serp_ai_overview_and_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_llm_settings",
        sa.Column("check_cadence", sa.String(16), nullable=False, server_default="weekly"),
    )


def downgrade() -> None:
    op.drop_column("client_llm_settings", "check_cadence")
