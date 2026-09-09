"""Scheduler checkpoints for daily sync.

Revision ID: 0018_scheduler_checkpoints
Revises: 0017_annotations_baseline
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_scheduler_checkpoints"
down_revision: Union[str, None] = "0017_annotations_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduler_checkpoints",
        sa.Column("name", sa.String(length=64), primary_key=True),
        sa.Column("last_run_date", sa.Date(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("scheduler_checkpoints")
