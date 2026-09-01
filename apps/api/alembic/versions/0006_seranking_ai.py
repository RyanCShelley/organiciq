"""Phase 5 SE Ranking AI staging + fact tables.

Revision ID: 0006_seranking_ai
Revises: 0005_ser_keyword_serp_features
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_seranking_ai"
down_revision: Union[str, None] = "0005_ser_keyword_serp_features"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staging_ser_ai_prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("llm_id", sa.String(64), nullable=True),
        sa.Column("prompt_id", sa.String(64), nullable=True),
        sa.Column("prompt_llm_id", sa.String(64), nullable=True),
        sa.Column("engine", sa.String(64), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("group_id", sa.String(64), nullable=True),
        sa.Column("group_name", sa.String(255), nullable=True),
        sa.Column("search_volume", sa.Numeric(), nullable=True),
        sa.Column("search_intent", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "staging_ser_ai_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("llm_id", sa.String(64), nullable=True),
        sa.Column("prompt_id", sa.String(64), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("url_position", sa.Numeric(), nullable=True),
        sa.Column("mention_position", sa.Numeric(), nullable=True),
        sa.Column("urls_count", sa.Numeric(), nullable=True),
        sa.Column("mentions_count", sa.Numeric(), nullable=True),
        sa.Column("organic_overlap_percent", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "facts_ser_ai_prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("llm_id", sa.String(64), nullable=False),
        sa.Column("prompt_id", sa.String(64), nullable=False),
        sa.Column("prompt_llm_id", sa.String(64), nullable=True),
        sa.Column("engine", sa.String(64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("group_id", sa.String(64), nullable=True),
        sa.Column("group_name", sa.String(255), nullable=True),
        sa.Column("search_volume", sa.Numeric(), nullable=True),
        sa.Column("search_intent", postgresql.JSONB(), nullable=True),
        sa.Column("url_position", sa.Numeric(), nullable=True),
        sa.Column("mention_position", sa.Numeric(), nullable=True),
        sa.Column("url_position_change", sa.Numeric(), nullable=True),
        sa.Column("mention_position_change", sa.Numeric(), nullable=True),
        sa.Column("brand_mentioned", sa.Boolean(), nullable=True),
        sa.Column("brand_cited", sa.Boolean(), nullable=True),
        sa.Column("citation_url", sa.Text(), nullable=True),
        sa.Column("ai_visibility", sa.Numeric(), nullable=True),
        sa.Column("ai_sov", sa.Numeric(), nullable=True),
        sa.Column("checked_at", sa.Date(), nullable=True),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topics.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("client_id", "llm_id", "prompt_id", name="uq_facts_ser_ai_prompts_grain"),
    )
    op.create_index("ix_facts_ser_ai_prompts_client", "facts_ser_ai_prompts", ["client_id"])

    op.create_table(
        "facts_ser_ai_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("llm_id", sa.String(64), nullable=False),
        sa.Column("prompt_id", sa.String(64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("url_position", sa.Numeric(), nullable=True),
        sa.Column("mention_position", sa.Numeric(), nullable=True),
        sa.Column("urls_count", sa.Numeric(), nullable=True),
        sa.Column("mentions_count", sa.Numeric(), nullable=True),
        sa.Column("organic_overlap_percent", sa.Numeric(), nullable=True),
        sa.Column("brand_mentioned", sa.Boolean(), nullable=True),
        sa.Column("brand_cited", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "client_id",
            "date",
            "llm_id",
            "prompt_id",
            name="uq_facts_ser_ai_checks_grain",
        ),
    )
    op.create_index("ix_facts_ser_ai_checks_client_date", "facts_ser_ai_checks", ["client_id", "date"])


def downgrade() -> None:
    op.drop_index("ix_facts_ser_ai_checks_client_date", table_name="facts_ser_ai_checks")
    op.drop_table("facts_ser_ai_checks")
    op.drop_index("ix_facts_ser_ai_prompts_client", table_name="facts_ser_ai_prompts")
    op.drop_table("facts_ser_ai_prompts")
    op.drop_table("staging_ser_ai_checks")
    op.drop_table("staging_ser_ai_prompts")
