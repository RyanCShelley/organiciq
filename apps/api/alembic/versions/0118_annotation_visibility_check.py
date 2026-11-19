"""Add visibility_check annotation type for monthly search visibility checks. Additive.

Revision ID: 0118_annotation_visibility_check
Revises: 0117_inlink_sentence
"""

from alembic import op

revision = "0118_annotation_visibility_check"
down_revision = "0117_inlink_sentence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE annotation_type ADD VALUE IF NOT EXISTS 'visibility_check'")


def downgrade() -> None:
    # A value cannot be dropped from a Postgres enum; an unused one is harmless.
    pass
