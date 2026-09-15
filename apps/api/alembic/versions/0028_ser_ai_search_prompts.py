"""Prompts a target appears in, from SE Ranking's AI Search API.

Backs the "untracked prompts" view: the difference between prompts the brand
actually shows up for and the prompts tracked in the SE Ranking project.

Also adds sync_jobs.params_json, so a job can carry run options — this source
needs an engine and a prompt count, and encoding those into the source string
would have been worse.

Revision ID: 0028_ser_ai_search_prompts
Revises: 0027_ser_domain_keywords
Create Date: 2026-09-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_ser_ai_search_prompts"
down_revision: Union[str, None] = "0027_ser_domain_keywords"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sync_jobs", sa.Column("params_json", postgresql.JSONB(), nullable=True))

    op.create_table(
        "facts_ser_ai_search_prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        sa.Column("engine", sa.String(64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("volume", sa.Numeric(), nullable=True),
        sa.Column("appearance_type", sa.String(64), nullable=True),
        sa.Column("answer_links", postgresql.JSONB(), nullable=True),
        sa.Column("snapshot_date", sa.Date(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "client_id", "engine", "prompt", name="uq_facts_ser_ai_search_prompts_grain"
        ),
    )
    op.create_index(
        "ix_facts_ser_ai_search_prompts_client",
        "facts_ser_ai_search_prompts",
        ["client_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_facts_ser_ai_search_prompts_client", table_name="facts_ser_ai_search_prompts"
    )
    op.drop_table("facts_ser_ai_search_prompts")
    op.drop_column("sync_jobs", "params_json")
