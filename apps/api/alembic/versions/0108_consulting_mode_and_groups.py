"""How we work with a client (execute the work, or consult and hand a report to their team) and groups of clients (Flint's sites). Additive.

Revision ID: 0108_consulting_mode_and_groups
Revises: 0107_annotation_event_type
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0108_consulting_mode_and_groups"
down_revision = "0107_annotation_event_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_groups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column("clients", sa.Column("service_mode", sa.String(16), nullable=False, server_default="execution"))
    op.add_column("clients", sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("client_groups.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_clients_group", "clients", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_clients_group", table_name="clients")
    op.drop_column("clients", "group_id")
    op.drop_column("clients", "service_mode")
    op.drop_table("client_groups")
