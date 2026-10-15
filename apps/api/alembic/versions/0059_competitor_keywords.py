"""Keywords the closest competitors rank for.

The content gap analysis found demand from Search Console, which only knows
queries the site was already shown for. A competitor's top-ranking terms are
demand the site has not been shown for at all.

Revision ID: 0059_competitor_keywords
Revises: 0058_gsc_pages_url_index
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0059_competitor_keywords"
down_revision = "0058_gsc_pages_url_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "facts_ser_competitor_keywords",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("competitor_domain", sa.String(255), nullable=False),
        sa.Column("keyword", sa.String(512), nullable=False),
        sa.Column("position", sa.Numeric, nullable=True),
        sa.Column("volume", sa.Numeric, nullable=True),
        sa.Column("difficulty", sa.Numeric, nullable=True),
        sa.Column("cpc", sa.Numeric, nullable=True),
        sa.Column("ranking_url", sa.Text, nullable=True),
        sa.Column("fetched_at", sa.Date, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "client_id", "competitor_domain", "keyword", name="uq_ser_competitor_keywords_grain"
        ),
    )
    op.create_index(
        "ix_ser_competitor_keywords_client", "facts_ser_competitor_keywords", ["client_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ser_competitor_keywords_client", table_name="facts_ser_competitor_keywords")
    op.drop_table("facts_ser_competitor_keywords")
