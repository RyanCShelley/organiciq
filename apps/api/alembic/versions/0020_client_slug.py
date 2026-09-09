"""Add unique client.slug for clean workspace URLs.

Revision ID: 0020_client_slug
Revises: 0019_ga4_engaged_sessions
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import re
import sqlalchemy as sa
from alembic import op

revision: str = "0020_client_slug"
down_revision: Union[str, None] = "0019_ga4_engaged_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _slugify(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "client"


def upgrade() -> None:
    op.add_column("clients", sa.Column("slug", sa.String(length=120), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, client_name FROM clients")).fetchall()
    used: set[str] = set()
    for client_id, client_name in rows:
        base = _slugify(str(client_name or "client"))
        slug = base
        n = 2
        while slug in used:
            slug = f"{base}-{n}"
            n += 1
        used.add(slug)
        conn.execute(
            sa.text("UPDATE clients SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": client_id},
        )

    op.alter_column("clients", "slug", existing_type=sa.String(length=120), nullable=False)
    op.create_index("ix_clients_slug", "clients", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_clients_slug", table_name="clients")
    op.drop_column("clients", "slug")
