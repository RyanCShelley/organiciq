"""Tag crawl issues with their source, like page snapshots already are.

The Decision Engine is moving to read the first-party crawl. Issues need the
same separation snapshots have, or the two crawlers' site-level findings mix and
whichever wrote last decides what the engine sees.

Revision ID: 0032_crawl_issue_source
Revises: 0031_client_crawl_page_limit
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_crawl_issue_source"
down_revision: Union[str, None] = "0031_client_crawl_page_limit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "facts_crawl_page_issues",
        sa.Column("source", sa.String(32), nullable=False, server_default="se_ranking_audit"),
    )
    op.create_index(
        "ix_facts_crawl_page_issues_client_source",
        "facts_crawl_page_issues",
        ["client_id", "source"],
    )


def downgrade() -> None:
    op.execute("DELETE FROM facts_crawl_page_issues WHERE source <> 'se_ranking_audit'")
    op.drop_index("ix_facts_crawl_page_issues_client_source", table_name="facts_crawl_page_issues")
    op.drop_column("facts_crawl_page_issues", "source")
