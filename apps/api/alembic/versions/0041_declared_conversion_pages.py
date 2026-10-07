"""Declared conversion pages, and a refresh-queue stub.

Which pages count as a conversion was guessed from URL fragments written
for somebody else's site. A client can now say.

Revision ID: 0041_declared_conversion_pages
Revises: 0040_keyword_page_map
"""

from alembic import op
import sqlalchemy as sa

revision = "0041_declared_conversion_pages"
down_revision = "0040_keyword_page_map"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_conversion_pages",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", sa.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("stage", sa.String(8), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "normalized_url", name="uq_client_conversion_page"),
    )
    op.create_index(
        "ix_client_conversion_pages_client", "client_conversion_pages", ["client_id"]
    )

    # A stub: nothing populates it, and an empty table means the gate never
    # fires. It exists so the gate can be built and tested now.
    op.create_table(
        "refresh_queue",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", sa.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "client_id", "normalized_url", "month", name="uq_refresh_queue_grain"
        ),
    )
    op.create_index("ix_refresh_queue_client_month", "refresh_queue", ["client_id", "month"])


def downgrade() -> None:
    op.drop_index("ix_refresh_queue_client_month", table_name="refresh_queue")
    op.drop_table("refresh_queue")
    op.drop_index("ix_client_conversion_pages_client", table_name="client_conversion_pages")
    op.drop_table("client_conversion_pages")
