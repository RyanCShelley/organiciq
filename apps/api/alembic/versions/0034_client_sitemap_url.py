"""A declared sitemap, for sites where discovery cannot find one.

coastalmechanical.com answers every unknown path with the site's HTML —
including /robots.txt — so nothing is discoverable there by any crawler. Rather
than guess forever, let the site be told where its sitemap is.

Revision ID: 0034_client_sitemap_url
Revises: 0033_internal_link_graph
Create Date: 2026-09-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034_client_sitemap_url"
down_revision: Union[str, None] = "0033_internal_link_graph"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("sitemap_url", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "sitemap_url")
