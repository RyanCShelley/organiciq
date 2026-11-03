"""Content calendar, and the SEO lead and content manager roles. Additive.

Revision ID: 0095_content_calendar
Revises: 0094_content_analysis
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0095_content_calendar"
down_revision = "0094_content_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A new enum value cannot be used in the transaction that adds it; nothing here uses it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'seo_lead'")
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'content_manager'")
    op.create_table(
        "content_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("source_area", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("source_key", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="idea"),
        sa.Column("due", sa.Date(), nullable=True),
        sa.Column("assignee_email", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("teamwork_task_id", sa.String(64), nullable=True),
        sa.Column("teamwork_task_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_content_items_client_due", "content_items", ["client_id", "due"])


def downgrade() -> None:
    op.drop_index("ix_content_items_client_due", table_name="content_items")
    op.drop_table("content_items")
