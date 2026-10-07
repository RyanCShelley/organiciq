"""What one lead is worth to this client.

Without it every client's lead is worth the same, and a leaking page on an
AC company's site — where one job is five figures — ranks alongside one on
a site selling a $40 subscription.

Revision ID: 0042_lead_value
Revises: 0041_declared_conversion_pages
"""

from alembic import op
import sqlalchemy as sa

revision = "0042_lead_value"
down_revision = "0041_declared_conversion_pages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("lead_value", sa.Numeric(), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "lead_value")
