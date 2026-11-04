"""Tasks an operator confirms from the Decision engine, and where they went.

Revision ID: 0078_engine_tasks
Revises: 0077_facts_bing_query_stats
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0078_engine_tasks"
down_revision = "0077_facts_bing_query_stats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "engine_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("rule_id", sa.String(16), nullable=False),
        sa.Column("search", sa.Text, nullable=False),
        sa.Column("page_url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("why", sa.Text, nullable=True),
        sa.Column("steps", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("done_when", sa.Text, nullable=True),
        sa.Column("metric", sa.Text, nullable=True),
        sa.Column("effort_min", sa.Integer, nullable=True),
        sa.Column("evidence", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="confirmed"),
        sa.Column("confirmed_by", sa.String(255), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("assignee_email", sa.String(255), nullable=True),
        sa.Column("due", sa.Date, nullable=True),
        sa.Column("teamwork_task_id", sa.String(64), nullable=True),
        sa.Column("teamwork_task_url", sa.Text, nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("client_id", "month", "rule_id", "search", "page_url", name="uq_engine_task_once"),
    )
    op.create_index("ix_engine_tasks_client_month", "engine_tasks", ["client_id", "month"])


def downgrade() -> None:
    op.drop_index("ix_engine_tasks_client_month", table_name="engine_tasks")
    op.drop_table("engine_tasks")
