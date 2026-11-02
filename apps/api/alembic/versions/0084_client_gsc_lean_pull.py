"""A per-client switch for the lean Search Console pull.

Lean pulls the per-search rows at one row per search and page per day for the last 120 days and per month before that,
without country and device. Off (the default) keeps the full pull every existing client has.

Revision ID: 0084_client_gsc_lean_pull
Revises: 0083_monthly_review_snapshots
"""

import sqlalchemy as sa
from alembic import op

revision = "0084_client_gsc_lean_pull"
down_revision = "0083_monthly_review_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("gsc_lean_pull", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("clients", "gsc_lean_pull")
