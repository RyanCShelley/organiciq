"""One saved record per client per month.

The engine recomputes on every page view. That makes the page a different
thing each time it loads: a run that named Visibility in the morning can name
Leads in the afternoon because a sync landed, and nothing records that it
changed or what the earlier answer was.

Almost everything the spec asks for downstream depends on a run being a thing
that happened rather than a thing recalculated. `held_since` and the two-month
hysteresis need last month's answer. "Do not prescribe this action on this URL
again before its check date" needs the date it was prescribed. The results
loop needs to know what was promised 28 to 45 days ago. None of that is
possible against a function.

The record is stored whole, as JSON, to `monthly-record.schema.json`. The
alternative was fifteen tables that have to be joined back into exactly the
shape the page reads, and every one of them a chance for the page to disagree
with the run.

Revision ID: 0046_monthly_records
Revises: 0045_keyword_targets
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0046_monthly_records"
down_revision = "0045_keyword_targets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        #: "2026-10". The grain is the month, not the day: a client gets one
        #: plan a month and re-running replaces it rather than adding to it.
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column(
            "run_saved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        #: The newest day the data behind this run actually covered. Not the
        #: day it was asked for — those differ, and the difference is the
        #: thing the page has to explain.
        sa.Column("data_through", sa.Date(), nullable=True),
        sa.Column("constraint_name", sa.String(length=32), nullable=False),
        #: The month this constraint was first named, for the two-month hold.
        sa.Column("held_since", sa.String(length=7), nullable=False),
        sa.Column("confidence", sa.String(length=8), nullable=False),
        #: The whole record, to monthly-record.schema.json.
        sa.Column("record", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("client_id", "month", name="uq_monthly_records_grain"),
    )
    op.create_index(
        "ix_monthly_records_client_month",
        "monthly_records",
        ["client_id", "month"],
    )

    op.create_table(
        "engine_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        #: Stable across re-runs of the same month, so workflow state set on
        #: Monday survives a re-run on Tuesday.
        sa.Column("uid", sa.String(length=128), nullable=False),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="action"),
        sa.Column(
            "assignee_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("due", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planned"),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipped_on", sa.Date(), nullable=True),
        #: The results loop. Filled on the check date, not at prescription.
        sa.Column("before_value", sa.Numeric(), nullable=True),
        sa.Column("after_value", sa.Numeric(), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("client_id", "uid", name="uq_engine_actions_uid"),
    )
    op.create_index(
        "ix_engine_actions_client_month", "engine_actions", ["client_id", "month"]
    )
    op.create_check_constraint(
        "ck_engine_actions_status",
        "engine_actions",
        "status IN ('planned', 'assigned', 'done', 'skipped')",
    )
    op.create_check_constraint(
        "ck_engine_actions_result",
        "engine_actions",
        "result IS NULL OR result IN ('improved', 'no_change', 'worse', 'waiting')",
    )


def downgrade() -> None:
    op.drop_table("engine_actions")
    op.drop_table("monthly_records")
