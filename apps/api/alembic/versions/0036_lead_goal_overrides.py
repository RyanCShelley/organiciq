"""Per-checkpoint lead goal overrides.

Revision ID: 0036_lead_goal_overrides
Revises: 0035_client_path_prefix
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0036_lead_goal_overrides"
down_revision = "0035_client_path_prefix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keyed by checkpoint month ("3", "6", ...). Separate from the frozen
    # projection so re-running the projection does not discard a correction
    # someone made deliberately.
    op.add_column(
        "clients",
        sa.Column(
            "lead_goal_overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("clients", "lead_goal_overrides")
