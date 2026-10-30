"""LLM visibility: runs, responses and per-client brand patterns.

Revision ID: 0079_llm_visibility
Revises: 0078_engine_tasks
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0079_llm_visibility"
down_revision = "0078_engine_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_llm_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False, unique=True),
        sa.Column("brand_name", sa.String(255), nullable=True),
        sa.Column("brand_patterns", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("competitors", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "llm_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("platforms", postgresql.ARRAY(sa.String(16)), nullable=False, server_default="{}"),
        sa.Column("total_calls", sa.Integer, nullable=True),
        sa.Column("total_errors", sa.Integer, nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("triggered_by", sa.String(255), nullable=True),
    )
    op.create_index("ix_llm_runs_client_started", "llm_runs", ["client_id", "started_at"])
    op.create_table(
        "llm_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("llm_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("topic_cluster", sa.String(160), nullable=True),
        sa.Column("keyword", sa.String(400), nullable=True),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("visibility_type", sa.String(24), nullable=True),
        sa.Column("brand_mentioned", sa.Boolean, nullable=True),
        sa.Column("url_cited", sa.Boolean, nullable=True),
        sa.Column("cited_urls", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("position", sa.String(64), nullable=True),
        sa.Column("sources_count", sa.Integer, nullable=True),
        sa.Column("competitors_mentioned", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("all_brands_ordered", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("other_brands_mentioned", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("brand_rank", sa.Integer, nullable=True),
        sa.Column("total_brands", sa.Integer, nullable=True),
        sa.Column("full_response", sa.Text, nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_llm_responses_run", "llm_responses", ["run_id"])
    op.create_index("ix_llm_responses_client_created", "llm_responses", ["client_id", "created_at"])


def downgrade() -> None:
    op.drop_table("llm_responses")
    op.drop_table("llm_runs")
    op.drop_table("client_llm_settings")
