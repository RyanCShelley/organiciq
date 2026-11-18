"""The "People also ask" questions of a SERP pull. Additive.

The pull already said whether the page had a "People also ask" box; the questions in it were dropped. They are
kept so a growth action can check which of them the page does not answer. None means the pull predates this.

Revision ID: 0115_serp_questions
Revises: 0114_serp_results_and_reading
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0115_serp_questions"
down_revision = "0114_serp_results_and_reading"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("facts_serp_features", sa.Column("questions", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("facts_serp_features", "questions")
