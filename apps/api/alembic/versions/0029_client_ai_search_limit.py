"""Per-client ceiling on AI-search prompt discovery.

prompts-by-target bills 200 credits per returned prompt, so the sensible number
differs by account: most clients want a handful, a few high-value ones justify
more. A single global constant would either overspend on small accounts or
starve the large ones.

Null means "use the default" (5), so existing clients need no backfill.

Revision ID: 0029_client_ai_search_limit
Revises: 0028_ser_ai_search_prompts
Create Date: 2026-09-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_client_ai_search_limit"
down_revision: Union[str, None] = "0028_ser_ai_search_prompts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("ai_search_prompt_limit", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "ai_search_prompt_limit")
