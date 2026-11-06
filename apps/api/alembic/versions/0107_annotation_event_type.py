"""An annotation type for events and trade shows, so their impact can be followed like any other change. Additive.

Revision ID: 0107_annotation_event_type
Revises: 0106_annotation_verified_how
"""

from alembic import op

revision = "0107_annotation_event_type"
down_revision = "0106_annotation_verified_how"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE annotation_type ADD VALUE IF NOT EXISTS 'event'")


def downgrade() -> None:
    # A value cannot be dropped from a Postgres enum; an unused one is harmless.
    pass
