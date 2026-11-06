"""How an annotation's change was seen live on the page (what was read, from where, when), when the live check wrote it. Additive.

Revision ID: 0106_annotation_verified_how
Revises: 0105_engine_task_parts
"""

import sqlalchemy as sa
from alembic import op

revision = "0106_annotation_verified_how"
down_revision = "0105_engine_task_parts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("annotations", sa.Column("verified_how", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("annotations", "verified_how")
