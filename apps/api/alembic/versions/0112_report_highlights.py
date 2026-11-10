"""The consultant's analysis as three short lists (going well, to watch, biggest gaps) beside the intro. Additive.

Revision ID: 0112_report_highlights
Revises: 0111_consulting_reports
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0112_report_highlights"
down_revision = "0111_consulting_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("consulting_reports", sa.Column("highlights", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    op.drop_column("consulting_reports", "highlights")
