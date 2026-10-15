"""Lead exclusions: slices of lead events that are test submissions.

Revision ID: 0063_lead_exclusions
Revises: 0062_annotation_engine_uid
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0063_lead_exclusions"
down_revision = "0062_annotation_engine_uid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_exclusions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("url_pattern", sa.Text(), nullable=True),
        sa.Column("event_name", sa.String(255), nullable=True),
        sa.Column("session_source", sa.String(255), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_lead_exclusions_client", "lead_exclusions", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_lead_exclusions_client", table_name="lead_exclusions")
    op.drop_table("lead_exclusions")
