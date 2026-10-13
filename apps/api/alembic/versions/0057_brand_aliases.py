"""Other names a client's brand is searched by.

`brand_terms` knew the client name and the domain. ACCTek is searched as
"acc technical services", which contains neither, so its brand queries read
as topics and a link was prescribed on the strength of one.

Revision ID: 0057_brand_aliases
Revises: 0056_plan_cadence
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0057_brand_aliases"
down_revision = "0056_plan_cadence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("brand_aliases", JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("clients", "brand_aliases")
