"""Every new client pulls Search Console lean by default.

Existing clients keep their setting: switching one changes the rows it stores, so it is done per client (a switch in
Admin) and replaces that client's rows safely.

Revision ID: 0085_gsc_lean_default_on
Revises: 0084_client_gsc_lean_pull
"""

import sqlalchemy as sa
from alembic import op

revision = "0085_gsc_lean_default_on"
down_revision = "0084_client_gsc_lean_pull"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("clients", "gsc_lean_pull", server_default=sa.true())


def downgrade() -> None:
    op.alter_column("clients", "gsc_lean_pull", server_default=sa.false())
