"""Engine action provenance and the Teamwork link.

`engine_actions.uid` is keyed on the slot (`{slug}-{month}-s{n}`), which keeps
an assignment alive across a re-run of the same month. With a Re-run button on
the client page that stability becomes a hazard: if a re-run changes what slot
1 *is*, yesterday's assignment silently points at a different action. Storing
the action id and URL that were on screen when somebody assigned it lets the
page say so instead of quietly lying.

`teamwork_task_id` is the other half of "sent" — without it, a task pushed to
Teamwork cannot be linked back to, or recognised on a second press.

Revision ID: 0049_engine_action_provenance
Revises: 0048_client_overrides
"""

from alembic import op
import sqlalchemy as sa

revision = "0049_engine_action_provenance"
down_revision = "0048_client_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "engine_actions",
        sa.Column("action_id", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "engine_actions",
        sa.Column("target_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "engine_actions",
        sa.Column("teamwork_task_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "engine_actions",
        sa.Column("teamwork_task_url", sa.Text(), nullable=True),
    )
    # Where this client's tasks go. One Teamwork site and token for the
    # install; the tasklist is the only per-client part.
    op.add_column(
        "clients",
        sa.Column("teamwork_tasklist_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clients", "teamwork_tasklist_id")
    op.drop_column("engine_actions", "teamwork_task_url")
    op.drop_column("engine_actions", "teamwork_task_id")
    op.drop_column("engine_actions", "target_url")
    op.drop_column("engine_actions", "action_id")
