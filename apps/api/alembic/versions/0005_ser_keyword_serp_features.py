"""Add earned SERP features to facts_ser_keywords.

Revision ID: 0005_ser_keyword_serp_features
Revises: 0004_seranking_search
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_ser_keyword_serp_features"
down_revision: Union[str, None] = "0004_seranking_search"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "facts_ser_keywords",
        sa.Column("earned_serp_features", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("facts_ser_keywords", "earned_serp_features")
