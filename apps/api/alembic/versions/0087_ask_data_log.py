"""Ask the data: a log of each question, its queries and cost.

Additive. The read-only role and the row policies it runs under are created by `app.ask.schema.ensure` the first time a
question is asked (idempotent). Row-level security is enabled on the listed tables but its policies are `to ask_data_reader`
only; the application's own role owns the tables and is not subject to it, so v1 and v2 are unaffected.

Revision ID: 0087_ask_data_log
Revises: 0086_ga4_engagement_seconds
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0087_ask_data_log"
down_revision = "0086_ga4_engagement_seconds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ask_data_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asked_by", sa.String(255), nullable=False),
        sa.Column("depth", sa.String(16), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("queries", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ask_data_log_client_created", "ask_data_log", ["client_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ask_data_log_client_created", table_name="ask_data_log")
    op.drop_table("ask_data_log")
