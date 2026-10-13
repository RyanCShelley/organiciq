"""How often a plan's allowances are spent.

Legacy clients buy one new page, one refresh and one growth action per
*quarter*. The allowances are plain monthly integers, so there was no way
to say that: at 1 the engine plans one every month — three times what was
sold — and at 0 it plans nothing, ever.

Everything else is monthly, which is the default, so this migration changes
no existing behaviour on its own.

Revision ID: 0056_plan_cadence
Revises: 0055_content_freshness
"""

from alembic import op
import sqlalchemy as sa

revision = "0056_plan_cadence"
down_revision = "0055_content_freshness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tiers",
        sa.Column(
            "plan_cadence",
            sa.String(16),
            nullable=False,
            server_default="monthly",
        ),
    )


def downgrade() -> None:
    op.drop_column("tiers", "plan_cadence")
