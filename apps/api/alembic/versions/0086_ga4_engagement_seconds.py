"""Time on site: GA4 engaged time (userEngagementDuration, seconds) stored beside sessions on each traffic row.

Additive and nullable. Rows pulled before this migration stay NULL until the client's Google Analytics is pulled again.

Revision ID: 0086_ga4_engagement_seconds
Revises: 0085_gsc_lean_default_on
"""

import sqlalchemy as sa
from alembic import op

revision = "0086_ga4_engagement_seconds"
down_revision = "0085_gsc_lean_default_on"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("staging_ga4_traffic", sa.Column("engagement_seconds", sa.Numeric(), nullable=True))
    op.add_column("facts_ga4_traffic", sa.Column("engagement_seconds", sa.Numeric(), nullable=True))


def downgrade() -> None:
    op.drop_column("facts_ga4_traffic", "engagement_seconds")
    op.drop_column("staging_ga4_traffic", "engagement_seconds")
