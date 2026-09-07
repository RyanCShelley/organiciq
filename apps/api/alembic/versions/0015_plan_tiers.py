"""Organic IQ plan tiers: Legacy, Launch, Lift, Lead.

Revision ID: 0015_plan_tiers
Revises: 0014_client_settings
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_plan_tiers"
down_revision: Union[str, None] = "0014_client_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Stable IDs — existing "Standard" row becomes Launch so seeded clients keep working.
LEGACY_ID = "11111111-1111-1111-1111-111111111110"
LAUNCH_ID = "11111111-1111-1111-1111-111111111111"
LIFT_ID = "11111111-1111-1111-1111-111111111112"
LEAD_ID = "11111111-1111-1111-1111-111111111113"

TIERS = [
    # id, name, keywords, prompts, new content /q, refresh /q, growth actions /mo, cadence, conversion_limit, reporting
    (LEGACY_ID, "Legacy", 5, 5, 1, 1, 1, "monthly", 2, "legacy"),
    (LAUNCH_ID, "Launch", 10, 10, 3, 3, 1, "monthly", 3, "launch"),
    (LIFT_ID, "Lift", 20, 20, 6, 6, 3, "bi_weekly", 5, "lift"),
    (LEAD_ID, "Lead", 30, 30, 9, 10, 5, "weekly", 8, "lead"),
]


def upgrade() -> None:
    op.add_column(
        "tiers",
        sa.Column(
            "watchlist_cadence",
            sa.String(length=32),
            nullable=False,
            server_default="monthly",
        ),
    )

    # Remap any clients on unknown tiers to Launch before reshaping the catalog.
    op.execute(
        sa.text(
            f"""
            UPDATE clients
            SET tier_id = '{LAUNCH_ID}'
            WHERE tier_id NOT IN ('{LEGACY_ID}', '{LAUNCH_ID}', '{LIFT_ID}', '{LEAD_ID}')
            """
        )
    )

    # Drop non-catalog tiers that are no longer referenced.
    op.execute(
        sa.text(
            f"""
            DELETE FROM tiers
            WHERE id NOT IN ('{LEGACY_ID}', '{LAUNCH_ID}', '{LIFT_ID}', '{LEAD_ID}')
            """
        )
    )

    for (
        tier_id,
        name,
        keywords,
        prompts,
        content,
        refresh,
        growth,
        cadence,
        conversion_limit,
        reporting,
    ) in TIERS:
        op.execute(
            sa.text(
                f"""
                INSERT INTO tiers (
                    id, tier_name, tracked_keyword_limit, tracked_prompt_limit,
                    content_allowance, update_allowance, growth_action_allowance,
                    conversion_limit, reporting_level, watchlist_cadence
                ) VALUES (
                    '{tier_id}', '{name}', {keywords}, {prompts},
                    {content}, {refresh}, {growth},
                    {conversion_limit}, '{reporting}', '{cadence}'
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

    # Unique name: remove leftover "Standard" if it somehow remains under another id.
    op.execute(sa.text("DELETE FROM tiers WHERE tier_name = 'Standard'"))


def downgrade() -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE clients SET tier_id = '{LAUNCH_ID}'
            WHERE tier_id IN ('{LEGACY_ID}', '{LIFT_ID}', '{LEAD_ID}')
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            DELETE FROM tiers
            WHERE id IN ('{LEGACY_ID}', '{LIFT_ID}', '{LEAD_ID}')
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE tiers SET
                tier_name = 'Standard',
                tracked_keyword_limit = 100,
                tracked_prompt_limit = 50,
                content_allowance = 4,
                update_allowance = 4,
                growth_action_allowance = 4,
                conversion_limit = 5,
                reporting_level = 'standard',
                watchlist_cadence = 'monthly'
            WHERE id = '{LAUNCH_ID}'
            """
        )
    )
    op.drop_column("tiers", "watchlist_cadence")
