"""Remember what a shipped task started from, and what it did.

Revision ID: 0082_engine_task_results
Revises: 0081_llm_asked_by_name
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0082_engine_task_results"
down_revision = "0081_llm_asked_by_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("engine_tasks", sa.Column("baseline", postgresql.JSONB, nullable=True))
    op.add_column("engine_tasks", sa.Column("check_on", sa.Date, nullable=True))
    op.add_column("engine_tasks", sa.Column("outcome", postgresql.JSONB, nullable=True))
    op.add_column("engine_tasks", sa.Column("outcome_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("engine_tasks", "outcome_at")
    op.drop_column("engine_tasks", "outcome")
    op.drop_column("engine_tasks", "check_on")
    op.drop_column("engine_tasks", "baseline")
