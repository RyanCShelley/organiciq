"""Content gaps and refreshes: items set aside, and the model's briefs and plans. Additive.

Revision ID: 0094_content_analysis
Revises: 0093_inlink_states
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0094_content_analysis"
down_revision = "0093_inlink_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("area", sa.String(16), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "area", "key", name="uq_content_state"),
    )
    op.create_table(
        "content_model_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("depth", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_content_model_runs_client_key", "content_model_runs", ["client_id", "kind", "key"])


def downgrade() -> None:
    op.drop_index("ix_content_model_runs_client_key", table_name="content_model_runs")
    op.drop_table("content_model_runs")
    op.drop_table("content_states")
