"""Client settings sheet URL + tier Growth Action allowance.

Revision ID: 0014_client_settings
Revises: 0013_ser_audit_staging
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_client_settings"
down_revision: Union[str, None] = "0013_ser_audit_staging"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("account_sheet_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "tiers",
        sa.Column(
            "growth_action_allowance",
            sa.Integer(),
            nullable=False,
            server_default="4",
        ),
    )


def downgrade() -> None:
    op.drop_column("tiers", "growth_action_allowance")
    op.drop_column("clients", "account_sheet_url")
