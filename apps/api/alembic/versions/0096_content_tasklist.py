"""A Teamwork tasklist for content calendar items, apart from the growth actions' one. Additive.

Revision ID: 0096_content_tasklist
Revises: 0095_content_calendar
"""

import sqlalchemy as sa
from alembic import op

revision = "0096_content_tasklist"
down_revision = "0095_content_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("teamwork_content_tasklist_id", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "teamwork_content_tasklist_id")
