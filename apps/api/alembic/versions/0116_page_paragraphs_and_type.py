"""Body paragraphs, page type and change history on the crawl, and a store for paragraph vectors. Additive.

The crawl kept headings and the first paragraph under each. Internal link suggestions need the body: which
paragraph a link belongs in, and how alike two pages are in what they say. A fingerprint of the paragraphs and
the version before the last change (kept 30 days) say when a page was updated and how. Every page also gets its
type, so contact, about and utility pages can be kept out as link sources.

Revision ID: 0116_page_paragraphs_and_type
Revises: 0115_serp_questions
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0116_page_paragraphs_and_type"
down_revision = "0115_serp_questions"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("page_type", sa.String(24)), ("paragraphs", JSONB), ("content_hash", sa.String(40)), ("content_changed_on", sa.Date),
    ("previous_paragraphs", JSONB), ("previous_replaced_on", sa.Date),
)


def upgrade() -> None:
    for name, kind in _COLUMNS:
        op.add_column("facts_crawl_page_snapshots", sa.Column(name, kind, nullable=True))
    op.create_table(
        "page_paragraph_vectors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("text_hash", sa.String(40), nullable=False),
        sa.Column("vector", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "text_hash", name="uq_page_paragraph_vectors_grain"),
    )


def downgrade() -> None:
    op.drop_table("page_paragraph_vectors")
    for name, _ in reversed(_COLUMNS):
        op.drop_column("facts_crawl_page_snapshots", name)
