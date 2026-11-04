"""Inlink suggester: what a person did with a suggested link (ignored, or confirmed live). Additive.

Revision ID: 0093_inlink_states
Revises: 0092_ctr_title_drafts
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0093_inlink_states"
down_revision = "0092_ctr_title_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inlink_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("anchor", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "source_url", "target_url", name="uq_inlink_state"),
    )


def downgrade() -> None:
    op.drop_table("inlink_states")
