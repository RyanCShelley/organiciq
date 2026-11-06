"""The Teamwork subtasks made for a task or a content item, so a send that stopped halfway finishes instead of repeating. Additive.

Revision ID: 0097_teamwork_subtasks
Revises: 0096_content_project
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0097_teamwork_subtasks"
down_revision = "0096_content_project"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("engine_tasks", "content_items"):
        op.add_column(table, sa.Column("teamwork_subtasks", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    for table in ("content_items", "engine_tasks"):
        op.drop_column(table, "teamwork_subtasks")
