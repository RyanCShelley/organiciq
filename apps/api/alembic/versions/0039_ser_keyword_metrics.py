"""Market data for keywords, ranked or not.

Difficulty for a term the client has no page for — the missing input behind
every "nothing ranks for this" estimate.

Revision ID: 0039_ser_keyword_metrics
Revises: 0038_crawl_render_and_cta
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0039_ser_keyword_metrics"
down_revision = "0038_crawl_render_and_cta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "facts_ser_keyword_metrics",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", sa.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("keyword", sa.String(512), nullable=False),
        sa.Column("source", sa.String(8), nullable=False, server_default="us"),
        sa.Column("volume", sa.Numeric(), nullable=True),
        sa.Column("difficulty", sa.Numeric(), nullable=True),
        sa.Column("cpc", sa.Numeric(), nullable=True),
        sa.Column("competition", sa.Numeric(), nullable=True),
        sa.Column("intents", postgresql.JSONB(), nullable=True),
        sa.Column("data_found", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fetched_at", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "keyword", "source", name="uq_ser_keyword_metrics_grain"),
    )
    op.create_index("ix_ser_keyword_metrics_client", "facts_ser_keyword_metrics", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_ser_keyword_metrics_client", table_name="facts_ser_keyword_metrics")
    op.drop_table("facts_ser_keyword_metrics")
