"""Per-client ceiling on site-crawl pages.

Sites differ by orders of magnitude — a brochure site is 40 pages, a blog
archive is 500, an e-commerce catalogue is effectively unbounded. One global
number would either truncate the large sites or waste a monthly crawl on the
small ones.

Null means "use the default" (500), so existing clients need no backfill.

Revision ID: 0031_client_crawl_page_limit
Revises: 0030_first_party_crawl
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_client_crawl_page_limit"
down_revision: Union[str, None] = "0030_first_party_crawl"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("crawl_page_limit", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "crawl_page_limit")
