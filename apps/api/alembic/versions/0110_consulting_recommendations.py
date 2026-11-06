"""Consulting recommendations (the briefs a consultant publishes to a client's portal), their audit trail, and a profile flag for AI visibility as a focus. Additive.

Revision ID: 0110_consulting_recommendations
Revises: 0109_consulting_profiles
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0110_consulting_recommendations"
down_revision = "0109_consulting_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("consulting_profiles", sa.Column("ai_visibility_focus", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_table(
        "consulting_recommendations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("focus", sa.String(8), nullable=False, server_default="seo"),
        sa.Column("source_kind", sa.String(24), nullable=False, server_default="manual"),
        sa.Column("source_ref", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("finding", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("cause_kind", sa.String(12), nullable=False, server_default="hypothesis"),
        sa.Column("cause_text", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("instructions", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("target_urls", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("priority", sa.String(8), nullable=False, server_default="medium"),
        sa.Column("expected_impact", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(8), nullable=False, server_default="medium"),
        sa.Column("confidence_reasons", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("effort_min", sa.Integer(), nullable=True),
        sa.Column("owner", sa.String(120), nullable=True),
        sa.Column("baseline", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("success_metrics", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("measure_on", sa.Date(), nullable=True),
        sa.Column("evidence", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("review_state", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.String(255), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("impl_status", sa.String(12), nullable=False, server_default="recommended"),
        sa.Column("impl_status_source", sa.String(12), nullable=True),
        sa.Column("impl_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("implemented_on", sa.Date(), nullable=True),
        sa.Column("implemented_on_estimated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("client_notes", sa.Text(), nullable=True),
        sa.Column("evidence_links", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("last_follow_up_on", sa.Date(), nullable=True),
        sa.Column("verification", sa.String(12), nullable=False, server_default="unverified"),
        sa.Column("verified_how", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_consulting_recs_client_state", "consulting_recommendations", ["client_id", "review_state"])
    op.create_table(
        "consulting_recommendation_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("recommendation_id", UUID(as_uuid=True), sa.ForeignKey("consulting_recommendations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("from_value", sa.String(64), nullable=True),
        sa.Column("to_value", sa.String(64), nullable=True),
        sa.Column("by", sa.String(255), nullable=False),
        sa.Column("detail", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_consulting_rec_events_rec", "consulting_recommendation_events", ["recommendation_id", "at"])


def downgrade() -> None:
    op.drop_index("ix_consulting_rec_events_rec", table_name="consulting_recommendation_events")
    op.drop_table("consulting_recommendation_events")
    op.drop_index("ix_consulting_recs_client_state", table_name="consulting_recommendations")
    op.drop_table("consulting_recommendations")
    op.drop_column("consulting_profiles", "ai_visibility_focus")
