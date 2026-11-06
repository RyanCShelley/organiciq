"""What we know about a consulting client's business and goals (the Understand step of the consulting workflow). Additive.

Revision ID: 0109_consulting_profiles
Revises: 0108_consulting_mode_and_groups
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0109_consulting_profiles"
down_revision = "0108_consulting_mode_and_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consulting_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("goals", sa.Text(), nullable=True),
        sa.Column("primary_objective", sa.Text(), nullable=True),
        sa.Column("audiences", sa.Text(), nullable=True),
        sa.Column("markets", sa.Text(), nullable=True),
        sa.Column("priority_services", sa.Text(), nullable=True),
        sa.Column("constraints", sa.Text(), nullable=True),
        sa.Column("editorial_rules", sa.Text(), nullable=True),
        sa.Column("resources", sa.Text(), nullable=True),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("consulting_profiles")
