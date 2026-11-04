"""The Teamwork project content goes to, and the list made for each calendar item. Additive.

Revision ID: 0096_content_project
Revises: 0095_content_calendar
"""

import sqlalchemy as sa
from alembic import op

revision = "0096_content_project"
down_revision = "0095_content_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("teamwork_content_project_id", sa.String(64), nullable=True))
    op.add_column("content_items", sa.Column("teamwork_tasklist_id", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("content_items", "teamwork_tasklist_id")
    op.drop_column("clients", "teamwork_content_project_id")
