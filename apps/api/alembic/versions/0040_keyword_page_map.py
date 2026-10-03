"""Which page is meant to own a term.

The one input no amount of data could supply, and the playbook's first
source for "which page should rank for this".

Revision ID: 0040_keyword_page_map
Revises: 0039_ser_keyword_metrics
"""

from alembic import op
import sqlalchemy as sa

revision = "0040_keyword_page_map"
down_revision = "0039_ser_keyword_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "keyword_page_map",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", sa.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("keyword", sa.String(512), nullable=False),
        sa.Column("page_url", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "keyword", name="uq_keyword_page_map_grain"),
    )
    op.create_index("ix_keyword_page_map_client", "keyword_page_map", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_keyword_page_map_client", table_name="keyword_page_map")
    op.drop_table("keyword_page_map")
