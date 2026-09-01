"""Phase 1 foundation schema + seed tier and AI channel rules.

Revision ID: 0001_phase1
Revises:
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_phase1"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    client_status = postgresql.ENUM(
        "active", "paused", "onboarding", "archived", name="client_status", create_type=False
    )
    user_role = postgresql.ENUM(
        "sma_admin", "sma_team", "client_admin", "client_viewer", name="user_role", create_type=False
    )
    integration_provider = postgresql.ENUM(
        "ga4", "gsc", "se_ranking", name="integration_provider", create_type=False
    )
    connection_status = postgresql.ENUM(
        "not_connected", "connected", "error", "disconnected", name="connection_status", create_type=False
    )
    sync_job_status = postgresql.ENUM(
        "queued",
        "fetching",
        "staging",
        "normalizing",
        "validating",
        "successful",
        "partial",
        "failed",
        name="sync_job_status",
        create_type=False,
    )
    validation_status = postgresql.ENUM(
        "pending", "passed", "failed", "skipped", name="validation_status", create_type=False
    )
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
    topic_status = postgresql.ENUM(
        "active", "paused", "archived", name="topic_status", create_type=False
    )

    bind = op.get_bind()
    for enum in (
        client_status,
        user_role,
        integration_provider,
        connection_status,
        sync_job_status,
        validation_status,
        organic_channel,
        topic_status,
    ):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "tiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tier_name", sa.String(100), nullable=False, unique=True),
        sa.Column("tracked_keyword_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tracked_prompt_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_allowance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("update_allowance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conversion_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reporting_level", sa.String(50), nullable=False, server_default="standard"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("tier_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tiers.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("primary_market", sa.String(255), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="America/New_York"),
        sa.Column("monthly_lead_goal", sa.Integer(), nullable=True),
        sa.Column("status", client_status, nullable=False, server_default="onboarding"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("google_sub", sa.String(255), nullable=True, unique=True),
        sa.Column("role", user_role, nullable=False, server_default="sma_team"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "user_clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="sma_team"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "client_id", name="uq_user_clients_user_client"),
    )

    op.create_table(
        "integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("provider", integration_provider, nullable=False),
        sa.Column("external_account_id", sa.String(255), nullable=True),
        sa.Column("external_property_id", sa.String(255), nullable=True),
        sa.Column("connection_status", connection_status, nullable=False, server_default="not_connected"),
        sa.Column("last_sync_started", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_completed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_sync", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fact_date", sa.Date(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("credentials", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("client_id", "provider", name="uq_integrations_client_provider"),
    )

    op.create_table(
        "sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sync_job_status, nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_fetched", sa.Integer(), nullable=True),
        sa.Column("records_written", sa.Integer(), nullable=True),
        sa.Column("fact_watermark", sa.Date(), nullable=True),
        sa.Column("validation_status", validation_status, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "uq_sync_jobs_active_client_source",
        "sync_jobs",
        ["client_id", "source"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('queued', 'fetching', 'staging', 'normalizing', 'validating')"
        ),
    )

    op.create_table(
        "data_watermarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("fact_through_date", sa.Date(), nullable=True),
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validation_status", validation_status, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "uq_data_watermarks_client_source",
        "data_watermarks",
        ["client_id", "source"],
        unique=True,
    )

    op.create_table(
        "conversion_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("event_name", sa.String(255), nullable=False),
        sa.Column("conversion_name", sa.String(255), nullable=False),
        sa.Column("conversion_type", sa.String(100), nullable=False, server_default="lead"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "channel_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("match_source", sa.String(255), nullable=True),
        sa.Column("match_medium", sa.String(255), nullable=True),
        sa.Column("match_host_contains", sa.String(255), nullable=True),
        sa.Column("channel", organic_channel, nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("topic_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", topic_status, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Seed default tier
    op.execute(
        sa.text(
            """
            INSERT INTO tiers (
                id, tier_name, tracked_keyword_limit, tracked_prompt_limit,
                content_allowance, update_allowance, conversion_limit, reporting_level
            ) VALUES (
                '11111111-1111-1111-1111-111111111111',
                'Standard',
                100, 50, 4, 4, 5, 'standard'
            )
            """
        )
    )

    # Seed AI channel rules + common channel mappings
    ai_hosts = ["chatgpt", "perplexity", "gemini", "claude", "copilot"]
    ai_ids = [
        "22000000-0000-4000-8000-000000000001",
        "22000000-0000-4000-8000-000000000002",
        "22000000-0000-4000-8000-000000000003",
        "22000000-0000-4000-8000-000000000004",
        "22000000-0000-4000-8000-000000000005",
    ]
    for i, host in enumerate(ai_hosts):
        op.execute(
            sa.text(
                f"""
                INSERT INTO channel_rules (
                    id, match_host_contains, channel, priority, active, description
                ) VALUES (
                    '{ai_ids[i]}',
                    '{host}',
                    'ai_referral',
                    {10 + i},
                    true,
                    'AI referral host: {host}'
                )
                """
            )
        )

    op.execute(
        sa.text(
            """
            INSERT INTO channel_rules (id, match_source, match_medium, channel, priority, active, description)
            VALUES
              ('33000000-0000-4000-8000-000000000001', 'google', 'organic', 'organic_search', 20, true, 'Google organic'),
              ('33000000-0000-4000-8000-000000000002', 'bing', 'organic', 'organic_search', 21, true, 'Bing organic'),
              ('33000000-0000-4000-8000-000000000003', '(direct)', '(none)', 'direct_unattributed', 30, true, 'Direct / unattributed'),
              ('33000000-0000-4000-8000-000000000004', 'google', 'cpc', 'paid_search', 40, true, 'Google paid search')
            """
        )
    )


def downgrade() -> None:
    op.drop_table("topics")
    op.drop_table("channel_rules")
    op.drop_table("conversion_definitions")
    op.drop_index("uq_data_watermarks_client_source", table_name="data_watermarks")
    op.drop_table("data_watermarks")
    op.drop_index("uq_sync_jobs_active_client_source", table_name="sync_jobs")
    op.drop_table("sync_jobs")
    op.drop_table("integrations")
    op.drop_table("user_clients")
    op.drop_table("users")
    op.drop_table("clients")
    op.drop_table("tiers")

    sa.Enum(name="topic_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="organic_channel").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="validation_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="sync_job_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="connection_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="integration_provider").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="client_status").drop(op.get_bind(), checkfirst=True)
