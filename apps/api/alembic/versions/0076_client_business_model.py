"""What kind of business a client is: lead generation, ecommerce, or both.

Revision ID: 0076_client_business_model
Revises: 0075_client_completion_patterns
"""

import sqlalchemy as sa
from alembic import op

revision = "0076_client_business_model"
down_revision = "0075_client_completion_patterns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("business_model", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "business_model")
