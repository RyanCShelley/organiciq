"""Phase 3 GA4 staging + fact tables.

Revision ID: 0003_ga4
Revises: 0002_gsc
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_ga4"
down_revision: Union[str, None] = "0002_gsc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

organic_channel = postgresql.ENUM(
    "organic_search",
    "ai_referral",
    "direct_unattributed",
    "paid_search",
    "referral",
    "social",
    "email",
    "other",
    name="organic_channel",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "staging_ga4_traffic",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("landing_page", sa.Text(), nullable=True),
        sa.Column("session_source", sa.String(255), nullable=True),
        sa.Column("session_medium", sa.String(255), nullable=True),
        sa.Column("sessions", sa.Numeric(), nullable=True),
        sa.Column("active_users", sa.Numeric(), nullable=True),
        sa.Column("views", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "staging_ga4_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("landing_page", sa.Text(), nullable=True),
        sa.Column("session_source", sa.String(255), nullable=True),
        sa.Column("session_medium", sa.String(255), nullable=True),
        sa.Column("event_name", sa.String(255), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "facts_ga4_traffic",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("raw_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("session_source", sa.String(255), nullable=False, server_default=""),
        sa.Column("session_medium", sa.String(255), nullable=False, server_default=""),
        sa.Column("channel", organic_channel, nullable=False),
        sa.Column("sessions", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("active_users", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("views", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "client_id",
            "date",
            "normalized_url",
            "channel",
            "session_source",
            "session_medium",
            name="uq_facts_ga4_traffic_grain",
        ),
    )
    op.create_index("ix_facts_ga4_traffic_client_date", "facts_ga4_traffic", ["client_id", "date"])

    op.create_table(
        "facts_ga4_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("raw_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("session_source", sa.String(255), nullable=False, server_default=""),
        sa.Column("session_medium", sa.String(255), nullable=False, server_default=""),
        sa.Column("channel", organic_channel, nullable=False),
        sa.Column("event_name", sa.String(255), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "client_id",
            "date",
            "normalized_url",
            "channel",
            "session_source",
            "session_medium",
            "event_name",
            name="uq_facts_ga4_events_grain",
        ),
    )
    op.create_index("ix_facts_ga4_events_client_date", "facts_ga4_events", ["client_id", "date"])


def downgrade() -> None:
    op.drop_index("ix_facts_ga4_events_client_date", table_name="facts_ga4_events")
    op.drop_table("facts_ga4_events")
    op.drop_index("ix_facts_ga4_traffic_client_date", table_name="facts_ga4_traffic")
    op.drop_table("facts_ga4_traffic")
    op.drop_table("staging_ga4_events")
    op.drop_table("staging_ga4_traffic")
