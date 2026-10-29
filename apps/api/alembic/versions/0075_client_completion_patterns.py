"""Page address patterns that mean a visitor finished (thank-you, order confirmation).

Revision ID: 0075_client_completion_patterns
Revises: 0074_client_bing_sites
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0075_client_completion_patterns"
down_revision = "0074_client_bing_sites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_completion_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False
        ),
        sa.Column("pattern", sa.String(255), nullable=False),
        sa.Column("label", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "pattern", name="uq_client_completion_pattern"),
    )


def downgrade() -> None:
    op.drop_table("client_completion_patterns")
