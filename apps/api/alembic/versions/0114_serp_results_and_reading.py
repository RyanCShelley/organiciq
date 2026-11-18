"""The ranking results of a SERP pull, and the reading of intent made from them. Additive.

Only the list of element types was kept, so nothing could say what kind of page ranks for a search. `results`
holds the top organic results as pulled; `reading` holds the model's structured reading of that page (intent,
content types and styles, evidence), stored so one pull is read once.

Revision ID: 0114_serp_results_and_reading
Revises: 0113_report_kind_and_notes
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0114_serp_results_and_reading"
down_revision = "0113_report_kind_and_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("facts_serp_features", sa.Column("results", JSONB, nullable=True))
    op.add_column("facts_serp_features", sa.Column("reading", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("facts_serp_features", "reading")
    op.drop_column("facts_serp_features", "results")
