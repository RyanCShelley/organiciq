"""Google's ranking updates, for drawing on the search visibility trend. Additive; not per client.

Revision ID: 0088_google_search_updates
Revises: 0087_ask_data_log
"""

import sqlalchemy as sa
from alembic import op

revision = "0088_google_search_updates"
down_revision = "0087_ask_data_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_search_updates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("begin", sa.Date(), nullable=False),
        sa.Column("end", sa.Date(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("google_search_updates")
