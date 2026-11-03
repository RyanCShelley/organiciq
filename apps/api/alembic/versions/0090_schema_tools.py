"""Schema and knowledge graph: approved Wikidata concepts per client, and the audits and markup generated for pages. Additive.

Revision ID: 0090_schema_tools
Revises: 0089_site_health_snapshots
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0090_schema_tools"
down_revision = "0089_site_health_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_schema_concepts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_key", sa.String(255), nullable=False),
        sa.Column("qid", sa.String(32), nullable=False),
        sa.Column("label", sa.String(500), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("approved_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "name_key", name="uq_client_schema_concept_name"),
    )
    op.create_table(
        "schema_page_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("depth", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_schema_page_reports_client_url", "schema_page_reports", ["client_id", "url", "kind"])


def downgrade() -> None:
    op.drop_index("ix_schema_page_reports_client_url", table_name="schema_page_reports")
    op.drop_table("schema_page_reports")
    op.drop_table("client_schema_concepts")
