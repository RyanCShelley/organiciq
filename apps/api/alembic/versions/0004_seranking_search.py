"""Phase 4 SE Ranking Search staging + fact tables.

Revision ID: 0004_seranking_search
Revises: 0003_ga4
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_seranking_search"
down_revision: Union[str, None] = "0003_ga4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staging_ser_keywords",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("site_engine_id", sa.String(64), nullable=True),
        sa.Column("keyword_id", sa.String(64), nullable=True),
        sa.Column("keyword", sa.Text(), nullable=True),
        sa.Column("group_id", sa.String(64), nullable=True),
        sa.Column("group_name", sa.String(255), nullable=True),
        sa.Column("volume", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "staging_ser_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("site_engine_id", sa.String(64), nullable=True),
        sa.Column("keyword_id", sa.String(64), nullable=True),
        sa.Column("keyword", sa.Text(), nullable=True),
        sa.Column("position", sa.Numeric(), nullable=True),
        sa.Column("position_change", sa.Numeric(), nullable=True),
        sa.Column("volume", sa.Numeric(), nullable=True),
        sa.Column("ranking_url", sa.Text(), nullable=True),
        sa.Column("visibility", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "staging_ser_competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("site_engine_id", sa.String(64), nullable=True),
        sa.Column("competitor_id", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("visibility", sa.Numeric(), nullable=True),
        sa.Column("metric_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "facts_ser_keywords",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("site_engine_id", sa.String(64), nullable=False),
        sa.Column("keyword_id", sa.String(64), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("group_id", sa.String(64), nullable=True),
        sa.Column("group_name", sa.String(255), nullable=True),
        sa.Column("volume", sa.Numeric(), nullable=True),
        sa.Column("current_position", sa.Numeric(), nullable=True),
        sa.Column("previous_position", sa.Numeric(), nullable=True),
        sa.Column("ranking_change", sa.Numeric(), nullable=True),
        sa.Column("visibility", sa.Numeric(), nullable=True),
        sa.Column("ranking_url", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.Date(), nullable=True),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topics.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "client_id",
            "site_engine_id",
            "keyword_id",
            name="uq_facts_ser_keywords_grain",
        ),
    )
    op.create_index("ix_facts_ser_keywords_client", "facts_ser_keywords", ["client_id"])

    op.create_table(
        "facts_ser_rankings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("site_engine_id", sa.String(64), nullable=False),
        sa.Column("keyword_id", sa.String(64), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("position", sa.Numeric(), nullable=True),
        sa.Column("position_change", sa.Numeric(), nullable=True),
        sa.Column("volume", sa.Numeric(), nullable=True),
        sa.Column("ranking_url", sa.Text(), nullable=True),
        sa.Column("visibility", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "client_id",
            "date",
            "site_engine_id",
            "keyword_id",
            name="uq_facts_ser_rankings_grain",
        ),
    )
    op.create_index("ix_facts_ser_rankings_client_date", "facts_ser_rankings", ["client_id", "date"])

    op.create_table(
        "facts_ser_competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("site_engine_id", sa.String(64), nullable=False),
        sa.Column("competitor_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("visibility", sa.Numeric(), nullable=True),
        sa.Column("metric_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "client_id",
            "site_engine_id",
            "competitor_id",
            name="uq_facts_ser_competitors_grain",
        ),
    )
    op.create_index("ix_facts_ser_competitors_client", "facts_ser_competitors", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_facts_ser_competitors_client", table_name="facts_ser_competitors")
    op.drop_table("facts_ser_competitors")
    op.drop_index("ix_facts_ser_rankings_client_date", table_name="facts_ser_rankings")
    op.drop_table("facts_ser_rankings")
    op.drop_index("ix_facts_ser_keywords_client", table_name="facts_ser_keywords")
    op.drop_table("facts_ser_keywords")
    op.drop_table("staging_ser_competitors")
    op.drop_table("staging_ser_positions")
    op.drop_table("staging_ser_keywords")
