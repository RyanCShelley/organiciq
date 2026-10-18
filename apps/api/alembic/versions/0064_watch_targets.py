"""Keyword and prompt strategic target states."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0064_watch_targets"
down_revision = "0063_baseline_versions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("watch_targets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("item_key", sa.String(128), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("target_url", sa.Text, nullable=True),
        sa.Column("priority", sa.Boolean, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("observation", JSONB, nullable=False),
        sa.UniqueConstraint("client_id", "kind", "item_key", name="uq_watch_targets_item"),
        sa.CheckConstraint("kind IN ('keyword', 'prompt')", name="ck_watch_targets_kind"),
        sa.CheckConstraint("state IN ('existing', 'planned', 'unmapped', 'excluded')", name="ck_watch_targets_state"),
    )
    op.create_index("ix_watch_targets_client", "watch_targets", ["client_id"])


def downgrade():
    op.drop_table("watch_targets")
