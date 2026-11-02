"""Keep each finished month's review once it has been worked out.

Revision ID: 0083_monthly_review_snapshots
Revises: 0082_engine_task_results
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0083_monthly_review_snapshots"
down_revision = "0082_engine_task_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_review_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("data_through", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.UniqueConstraint("client_id", "month", name="uq_monthly_review_snapshot"),
    )


def downgrade() -> None:
    op.drop_table("monthly_review_snapshots")
