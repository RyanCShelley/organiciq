"""Enterprise's growth-action allowance floor.

Enterprise is set per client, at five or more. The tier row carried zero,
and all three Enterprise clients have no per-client override — so whatever
the engine ranked, they were entitled to nothing. A floor of five means an
unset client gets the minimum rather than silence.

Revision ID: 0043_enterprise_allowance_floor
Revises: 0042_lead_value
"""

from alembic import op
import sqlalchemy as sa

revision = "0043_enterprise_allowance_floor"
down_revision = "0042_lead_value"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE tiers SET growth_action_allowance = 5 "
            "WHERE tier_name = 'Enterprise' AND growth_action_allowance < 5"
        )
    )


def downgrade() -> None:
    # The old value was zero, which is what this exists to stop. Going back
    # to it would silently re-entitle three clients to nothing, so the
    # downgrade is deliberately a no-op.
    pass
