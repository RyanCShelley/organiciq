"""Schema screen: things a person has said do not apply to a client. Additive.

Revision ID: 0091_schema_ignores
Revises: 0090_schema_tools
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0091_schema_ignores"
down_revision = "0090_schema_tools"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_schema_ignores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "scope", "key", name="uq_client_schema_ignore"),
    )


def downgrade() -> None:
    op.drop_table("client_schema_ignores")
