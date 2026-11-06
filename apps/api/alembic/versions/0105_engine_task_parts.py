"""The parts of an engine task (a growth action's rewrite the title, add internal links, ...), stored so each can point at its tool and be marked done. Additive.

Revision ID: 0105_engine_task_parts
Revises: 0104_ads_lsa_leads
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0105_engine_task_parts"
down_revision = "0104_ads_lsa_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("engine_tasks", sa.Column("parts", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))


def downgrade() -> None:
    op.drop_column("engine_tasks", "parts")
