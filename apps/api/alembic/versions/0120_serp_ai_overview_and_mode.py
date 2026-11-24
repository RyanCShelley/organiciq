"""Store Google AI Overview and AI Mode summaries on facts_serp_features. Additive.

Revision ID: 0120_serp_ai_overview_and_mode
Revises: 0119_phase3_decision_engine
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0120_serp_ai_overview_and_mode"
down_revision = "0119_phase3_decision_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("facts_serp_features", sa.Column("ai_overview", JSONB(), nullable=True))
    op.add_column("facts_serp_features", sa.Column("ai_mode", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("facts_serp_features", "ai_mode")
    op.drop_column("facts_serp_features", "ai_overview")
