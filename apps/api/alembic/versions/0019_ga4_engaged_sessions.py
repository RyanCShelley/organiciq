"""Add engaged_sessions for GA4 bounce rate.

Revision ID: 0019_ga4_engaged_sessions
Revises: 0018_scheduler_checkpoints
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_ga4_engaged_sessions"
down_revision: Union[str, None] = "0018_scheduler_checkpoints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "staging_ga4_traffic",
        sa.Column("engaged_sessions", sa.Numeric(), nullable=True),
    )
    op.add_column(
        "facts_ga4_traffic",
        sa.Column("engaged_sessions", sa.Numeric(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("facts_ga4_traffic", "engaged_sessions")
    op.drop_column("staging_ga4_traffic", "engaged_sessions")
