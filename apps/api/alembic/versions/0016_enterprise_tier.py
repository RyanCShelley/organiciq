"""Enterprise tier + per-client custom plan allowances.

Revision ID: 0016_enterprise_tier
Revises: 0015_plan_tiers
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_enterprise_tier"
down_revision: Union[str, None] = "0015_plan_tiers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENTERPRISE_ID = "11111111-1111-1111-1111-111111111114"


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("custom_tracked_keyword_limit", sa.Integer(), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("custom_tracked_prompt_limit", sa.Integer(), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("custom_content_allowance", sa.Integer(), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("custom_update_allowance", sa.Integer(), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("custom_growth_action_allowance", sa.Integer(), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("custom_watchlist_cadence", sa.String(length=32), nullable=True),
    )

    op.execute(
        sa.text(
            f"""
            INSERT INTO tiers (
                id, tier_name, tracked_keyword_limit, tracked_prompt_limit,
                content_allowance, update_allowance, growth_action_allowance,
                conversion_limit, reporting_level, watchlist_cadence
            ) VALUES (
                '{ENTERPRISE_ID}', 'Enterprise', 0, 0,
                0, 0, 0,
                0, 'enterprise', 'monthly'
            )
            ON CONFLICT (id) DO UPDATE SET
                tier_name = EXCLUDED.tier_name,
                tracked_keyword_limit = EXCLUDED.tracked_keyword_limit,
                tracked_prompt_limit = EXCLUDED.tracked_prompt_limit,
                content_allowance = EXCLUDED.content_allowance,
                update_allowance = EXCLUDED.update_allowance,
                growth_action_allowance = EXCLUDED.growth_action_allowance,
                conversion_limit = EXCLUDED.conversion_limit,
                reporting_level = EXCLUDED.reporting_level,
                watchlist_cadence = EXCLUDED.watchlist_cadence,
                updated_at = NOW()
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DELETE FROM tiers WHERE id = '{ENTERPRISE_ID}'"))
    op.drop_column("clients", "custom_watchlist_cadence")
    op.drop_column("clients", "custom_growth_action_allowance")
    op.drop_column("clients", "custom_update_allowance")
    op.drop_column("clients", "custom_content_allowance")
    op.drop_column("clients", "custom_tracked_prompt_limit")
    op.drop_column("clients", "custom_tracked_keyword_limit")
