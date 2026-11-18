"""The sentence written for a suggested link, kept on the link. Additive.

Some suggested links have no phrase in the source paragraph that can carry them, so a sentence has to be added.
The tool writes that sentence on request. It is kept with the link, with the link text it was written around, so
the whole team sees the same one and it is not written again.

Revision ID: 0117_inlink_sentence
Revises: 0116_page_paragraphs_and_type
"""

import sqlalchemy as sa
from alembic import op

revision = "0117_inlink_sentence"
down_revision = "0116_page_paragraphs_and_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inlink_states", sa.Column("sentence", sa.Text, nullable=True))
    op.add_column("inlink_states", sa.Column("sentence_anchor", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("inlink_states", "sentence_anchor")
    op.drop_column("inlink_states", "sentence")
