"""Client path scope, for a site that lives under a folder of a larger domain.

Revision ID: 0035_client_path_prefix
Revises: 0034_client_sitemap_url
"""

from alembic import op
import sqlalchemy as sa

revision = "0035_client_path_prefix"
down_revision = "0034_client_sitemap_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Null means the whole domain, which is every client but the rare one whose
    # site is a section of a parent brand's domain.
    op.add_column("clients", sa.Column("path_prefix", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "path_prefix")
