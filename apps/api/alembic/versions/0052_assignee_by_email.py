"""Assign a slot to somebody who has no OrganicIQ account.

`assignee_user_id` is a foreign key to `users`, so only people who can sign
in here could hold a slot. Most of the team does the work and never opens
this tool: of the eight people in Teamwork, four had an OrganicIQ account
and the rest could not be assigned anything.

Email is the identity in both systems — it is already how a sent task finds
its Teamwork owner — so it is what a slot stores. `assignee_user_id` stays
for the people who are both, and for the rows written before this.

Revision ID: 0052_assignee_by_email
Revises: 0051_serp_features
"""

from alembic import op
import sqlalchemy as sa

revision = "0052_assignee_by_email"
down_revision = "0051_serp_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "engine_actions", sa.Column("assignee_email", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "engine_actions", sa.Column("assignee_name", sa.String(length=255), nullable=True)
    )
    # Backfill from the accounts that could already hold a slot.
    op.execute(
        """
        UPDATE engine_actions AS e
           SET assignee_email = u.email, assignee_name = u.name
          FROM users AS u
         WHERE e.assignee_user_id = u.id
        """
    )


def downgrade() -> None:
    op.drop_column("engine_actions", "assignee_name")
    op.drop_column("engine_actions", "assignee_email")
