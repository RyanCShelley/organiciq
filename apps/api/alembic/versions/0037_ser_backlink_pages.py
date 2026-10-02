"""Per-URL backlink counts from SE Ranking.

Revision ID: 0037_ser_backlink_pages
Revises: 0036_lead_goal_overrides
"""

from alembic import op
import sqlalchemy as sa

revision = "0037_ser_backlink_pages"
down_revision = "0036_lead_goal_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "facts_ser_backlink_pages",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", sa.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("normalized_url", sa.String(1024), nullable=False),
        sa.Column("raw_url", sa.String(1024), nullable=False),
        sa.Column("backlinks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("refdomains", sa.Integer, nullable=False, server_default="0"),
        sa.Column("dofollow_backlinks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("nofollow_backlinks", sa.Integer, nullable=False, server_default="0"),
        # When SE Ranking first saw a link to this page. The reason for storing
        # it: a new referring domain is an event — a PR push landing — and a
        # count alone cannot tell you one happened.
        sa.Column("first_seen", sa.Date, nullable=True),
        sa.Column("last_visited", sa.Date, nullable=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "normalized_url", name="uq_ser_backlink_pages_grain"),
    )
    op.create_index(
        "ix_ser_backlink_pages_client", "facts_ser_backlink_pages", ["client_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ser_backlink_pages_client", table_name="facts_ser_backlink_pages")
    op.drop_table("facts_ser_backlink_pages")
