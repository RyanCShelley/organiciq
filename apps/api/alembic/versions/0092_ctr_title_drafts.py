"""CTR optimizer: title tags a model wrote for a page, from its search data. Additive.

Revision ID: 0092_ctr_title_drafts
Revises: 0091_schema_ignores
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0092_ctr_title_drafts"
down_revision = "0091_schema_ignores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ctr_title_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("depth", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("range_from", sa.String(10), nullable=False),
        sa.Column("range_to", sa.String(10), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ctr_title_drafts_client_url", "ctr_title_drafts", ["client_id", "url"])


def downgrade() -> None:
    op.drop_index("ix_ctr_title_drafts_client_url", table_name="ctr_title_drafts")
    op.drop_table("ctr_title_drafts")
