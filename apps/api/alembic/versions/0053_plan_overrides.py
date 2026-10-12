"""Let a person decide what is in the month's plan.

The engine ranks and fills the slots; it does not know that the team is on a
larger project this month, or that the capabilities pages are being rebuilt.
`in_plan` is where somebody says otherwise: null defers to the engine, true
puts an action in that the engine left out, false takes one out that it put
in. Keyed by the action's own uid, so the choice survives a re-run.

Revision ID: 0053_plan_overrides
Revises: 0052_assignee_by_email
"""

from alembic import op
import sqlalchemy as sa

revision = "0053_plan_overrides"
down_revision = "0052_assignee_by_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("engine_actions", sa.Column("in_plan", sa.Boolean(), nullable=True))
    op.add_column(
        "engine_actions", sa.Column("in_plan_reason", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("engine_actions", "in_plan_reason")
    op.drop_column("engine_actions", "in_plan")
