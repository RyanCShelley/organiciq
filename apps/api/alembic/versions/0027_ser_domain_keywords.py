"""Organic keywords the domain ranks for, from SE Ranking Domain Analysis.

Backs the "untracked keywords" view: the difference between what the domain
ranks for and what the watch list tracks. Stored rather than fetched live
because /domain/keywords costs 100 credits per request — one fetch should be
viewable many times, and the untracked set recomputes at read time as keywords
are added to tracking.

Revision ID: 0027_ser_domain_keywords
Revises: 0026_baseline_projection
Create Date: 2026-09-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_ser_domain_keywords"
down_revision: Union[str, None] = "0026_baseline_projection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "facts_ser_domain_keywords",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("position", sa.Numeric(), nullable=True),
        sa.Column("previous_position", sa.Numeric(), nullable=True),
        sa.Column("volume", sa.Numeric(), nullable=True),
        sa.Column("difficulty", sa.Numeric(), nullable=True),
        sa.Column("cpc", sa.Numeric(), nullable=True),
        sa.Column("traffic", sa.Numeric(), nullable=True),
        sa.Column("ranking_url", sa.Text(), nullable=True),
        sa.Column("serp_features", postgresql.JSONB(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "keyword", name="uq_facts_ser_domain_keywords_grain"),
    )
    op.create_index(
        "ix_facts_ser_domain_keywords_client", "facts_ser_domain_keywords", ["client_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_facts_ser_domain_keywords_client", table_name="facts_ser_domain_keywords")
    op.drop_table("facts_ser_domain_keywords")
