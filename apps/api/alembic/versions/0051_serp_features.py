"""Every SERP feature on a query, held or not.

`facts_ser_keywords.earned_serp_features` records what a client *won*, which
answers "what did we get" and not "what is on this page". V-5 and T-2 both
need the second question and have sat in BLOCKED_ACTIONS saying so.

Dated, because a SERP changes and an action judged in November should be
readable against the SERP that was there when it was prescribed.

Revision ID: 0051_serp_features
Revises: 0050_client_page_stages
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0051_serp_features"
down_revision = "0050_client_page_stages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "facts_serp_features",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id", sa.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False
        ),
        sa.Column("pulled_on", sa.Date(), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("location_code", sa.Integer(), nullable=False, server_default="2840"),
        # Every element type on the SERP, in DataForSEO's own spelling.
        sa.Column("item_types", postgresql.JSONB(), nullable=False),
        # Which domains hold each feature, so "the client does not hold it"
        # is read rather than assumed.
        sa.Column("holders", postgresql.JSONB(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="dataforseo"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "client_id", "pulled_on", "keyword", "location_code",
            name="uq_facts_serp_features_grain",
        ),
    )
    op.create_index(
        "ix_facts_serp_features_client_keyword",
        "facts_serp_features",
        ["client_id", "keyword"],
    )


def downgrade() -> None:
    op.drop_index("ix_facts_serp_features_client_keyword", table_name="facts_serp_features")
    op.drop_table("facts_serp_features")
