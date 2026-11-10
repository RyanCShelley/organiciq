"""A consulting report for one month: the consultant's own analysis, and the headline numbers frozen when it is published to the client. Additive.

Revision ID: 0111_consulting_reports
Revises: 0110_consulting_recommendations
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0111_consulting_reports"
down_revision = "0110_consulting_recommendations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consulting_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_month", sa.String(7), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("analysis", sa.Text(), nullable=True),
        sa.Column("review_state", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metrics_snapshot", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "period_month", name="uq_consulting_report_month"),
    )


def downgrade() -> None:
    op.drop_table("consulting_reports")
