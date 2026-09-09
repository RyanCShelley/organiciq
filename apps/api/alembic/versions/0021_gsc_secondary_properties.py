"""Add secondary GSC properties and staging site URL tags.

Revision ID: 0021_gsc_secondary_properties
Revises: 0020_client_slug
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_gsc_secondary_properties"
down_revision: Union[str, None] = "0020_client_slug"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "integrations",
        sa.Column(
            "gsc_secondary_site_urls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("staging_gsc_daily", sa.Column("gsc_site_url", sa.String(length=512), nullable=True))
    op.add_column("staging_gsc_pages", sa.Column("gsc_site_url", sa.String(length=512), nullable=True))
    op.add_column(
        "staging_gsc_query_pages",
        sa.Column("gsc_site_url", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("staging_gsc_query_pages", "gsc_site_url")
    op.drop_column("staging_gsc_pages", "gsc_site_url")
    op.drop_column("staging_gsc_daily", "gsc_site_url")
    op.drop_column("integrations", "gsc_secondary_site_urls")
