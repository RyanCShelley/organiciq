"""Separate current tracker membership from retained keyword history."""
from alembic import op
import sqlalchemy as sa

revision = "0068_ser_keyword_tracking"
down_revision = "0067_gsc_property_provenance"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("facts_ser_keywords", sa.Column("is_tracked", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column("facts_ser_keywords", "is_tracked")
