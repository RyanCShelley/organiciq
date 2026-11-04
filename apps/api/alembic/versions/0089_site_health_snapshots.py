"""Site health: each month's SEO and GEO scores, kept because the crawl they come from is replaced on every run. Additive.

Revision ID: 0089_site_health_snapshots
Revises: 0088_google_search_updates
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0089_site_health_snapshots"
down_revision = "0088_google_search_updates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_health_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("crawl_date", sa.Date(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "month", name="uq_site_health_client_month"),
    )


def downgrade() -> None:
    op.drop_table("site_health_snapshots")
