"""Phase 3 Decision Engine: reviewer rejection fields on engine_tasks and style_notes on clients. Additive.

Revision ID: 0119_phase3_decision_engine
Revises: 0118_annotation_visibility_check
"""

from alembic import op
import sqlalchemy as sa

revision = "0119_phase3_decision_engine"
down_revision = "0118_annotation_visibility_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("engine_tasks", sa.Column("rejection_reason", sa.String(32), nullable=True))
    op.add_column("engine_tasks", sa.Column("rejection_note", sa.Text(), nullable=True))
    op.add_column("engine_tasks", sa.Column("rejected_by", sa.String(255), nullable=True))
    op.add_column("engine_tasks", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("clients", sa.Column("style_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "style_notes")
    op.drop_column("engine_tasks", "rejected_at")
    op.drop_column("engine_tasks", "rejected_by")
    op.drop_column("engine_tasks", "rejection_note")
    op.drop_column("engine_tasks", "rejection_reason")
