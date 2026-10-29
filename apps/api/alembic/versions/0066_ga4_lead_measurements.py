"""Cache exact-period session lead measurements without rewriting legacy targets."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0066_ga4_lead_measurements"
down_revision = "0065_automatic_keyword_map"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("ga4_lead_measurements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("definition_key", sa.String(64), nullable=False),
        sa.Column("measurement", postgresql.JSONB(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", "start_date", "end_date", "definition_key", name="uq_ga4_lead_measurement_scope"))
    op.create_index("ix_ga4_lead_measurements_client_id", "ga4_lead_measurements", ["client_id"])


def downgrade():
    op.drop_table("ga4_lead_measurements")
