"""Store the frozen growth projection alongside the baseline.

growth_calculator already produced Today / 3 / 6 / 9 / 12-month checkpoints;
they were returned in the preview response and then discarded. They are the
benchmarks the account is measured against, so they are persisted with the
inputs that produced them and a `generated_on` date — the projection freezes
when the baseline is built and is re-run on demand, so a stale set has to be
visible as stale.

Revision ID: 0026_baseline_projection
Revises: 0025_baseline_period_window
Create Date: 2026-09-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_baseline_projection"
down_revision: Union[str, None] = "0025_baseline_period_window"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("baseline_projection_json", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clients", "baseline_projection_json")
