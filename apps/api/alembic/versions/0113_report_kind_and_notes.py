"""Two kinds of consulting report (monthly performance, executive summary) per month, and the consultant's short context note under each section. Additive.

Revision ID: 0113_report_kind_and_notes
Revises: 0112_report_highlights
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0113_report_kind_and_notes"
down_revision = "0112_report_highlights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("consulting_reports", sa.Column("kind", sa.String(12), nullable=False, server_default="monthly"))
    op.add_column("consulting_reports", sa.Column("notes", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.drop_constraint("uq_consulting_report_month", "consulting_reports", type_="unique")
    op.create_unique_constraint("uq_consulting_report_kind_month", "consulting_reports", ["client_id", "kind", "period_month"])


def downgrade() -> None:
    op.drop_constraint("uq_consulting_report_kind_month", "consulting_reports", type_="unique")
    op.create_unique_constraint("uq_consulting_report_month", "consulting_reports", ["client_id", "period_month"])
    op.drop_column("consulting_reports", "notes")
    op.drop_column("consulting_reports", "kind")
