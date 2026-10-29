"""Locked baselines, one row per version.

Revision ID: 0063_baseline_versions
Revises: 0062_annotation_engine_uid
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0063_baseline_versions"
down_revision = "0062_annotation_engine_uid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "baseline_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("reason_note", sa.Text, nullable=True),
        sa.Column("locked_by", sa.String(255), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("method_version", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(8), nullable=False),
        sa.Column("regime_start", sa.String(7), nullable=True),
        sa.Column("window_from", sa.String(7), nullable=False),
        sa.Column("window_to", sa.String(7), nullable=False),
        sa.Column("lead_events", JSONB, nullable=False),
        sa.Column("acknowledged", JSONB, nullable=False),
        sa.Column("monthly_sessions", sa.Numeric, nullable=True),
        sa.Column("monthly_organic_sessions", sa.Numeric, nullable=True),
        sa.Column("lead_rate_pct", sa.Numeric, nullable=True),
        sa.Column("monthly_leads", sa.Numeric, nullable=True),
        sa.Column("goal_monthly_leads", sa.Numeric, nullable=True),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.UniqueConstraint("client_id", "version", name="uq_baseline_versions_client_version"),
    )
    op.create_index("ix_baseline_versions_client", "baseline_versions", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_baseline_versions_client", table_name="baseline_versions")
    op.drop_table("baseline_versions")
