"""Preserve native GA4 channel observations without changing baseline extract grain."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0069_ga4_native_channels"
down_revision = "0068_ser_keyword_tracking"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        for value in ("paid_social", "display", "cross_network", "other_paid"):
            op.execute(f"ALTER TYPE organic_channel ADD VALUE IF NOT EXISTS '{value}'")
    op.add_column("clients", sa.Column("service_reporting", pg.JSONB(), nullable=True))
    for table in ("staging_ga4_traffic", "staging_ga4_events"):
        op.add_column(table, sa.Column("session_default_channel_group", sa.String(100), nullable=True))
        op.add_column(table, sa.Column("report_basis", sa.String(32), nullable=False, server_default="legacy"))
    op.create_table("ga4_native_channel_observations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", pg.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("raw_url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("session_source", sa.String(255), nullable=False),
        sa.Column("session_medium", sa.String(255), nullable=False),
        sa.Column("session_default_channel_group", sa.String(100), nullable=False),
        sa.Column("channel", pg.ENUM(name="organic_channel", create_type=False), nullable=False),
        sa.Column("event_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("sessions", sa.Numeric(), nullable=True),
        sa.Column("active_users", sa.Numeric(), nullable=True),
        sa.Column("views", sa.Numeric(), nullable=True),
        sa.Column("engaged_sessions", sa.Numeric(), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=True),
        sa.Column("channel_rule_version", sa.String(32), nullable=False, server_default="ga4-native-v1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "date", "normalized_url", "session_source", "session_medium", "session_default_channel_group", "event_name", name="uq_ga4_native_channel_grain"))
    op.create_index("ix_ga4_native_channel_client_date", "ga4_native_channel_observations", ["client_id", "date"])


def downgrade():
    op.drop_table("ga4_native_channel_observations")
    for table in ("staging_ga4_traffic", "staging_ga4_events"):
        op.drop_column(table, "report_basis")
        op.drop_column(table, "session_default_channel_group")
    op.drop_column("clients", "service_reporting")
    # Postgres enum labels remain; they do not rewrite existing observations.
