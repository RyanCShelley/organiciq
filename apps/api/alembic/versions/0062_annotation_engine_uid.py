"""Tie an annotation to the engine action whose shipping wrote it.

Revision ID: 0062_annotation_engine_uid
Revises: 0061_rename_dataforseo_jobs
"""

from alembic import op
import sqlalchemy as sa

revision = "0062_annotation_engine_uid"
down_revision = "0061_rename_dataforseo_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("annotations", sa.Column("engine_uid", sa.String(128), nullable=True))
    op.create_unique_constraint(
        "uq_annotations_engine_uid", "annotations", ["client_id", "engine_uid"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_annotations_engine_uid", "annotations", type_="unique")
    op.drop_column("annotations", "engine_uid")
