"""Let someone say "not this client" and "not this page".

Boys Electrical's traffic branch fails on a careers page: 52 sessions, no
conversions. The finding is arithmetically right and strategically useless —
nobody is being paid to recruit electricians this quarter — and there is
currently no way to say so. The engine will name it again next month, and the
month after.

Two different objections, so two mechanisms rather than one:

* **A page the engine should ignore.** Careers, investor relations, a
  support portal. Per client, because some agencies really are running
  recruitment campaigns and a global pattern list would decide that for
  everyone. Excluded pages are skipped as candidates and excluded from the
  session and lead totals that judge a branch.
* **A constraint somebody disagrees with.** Not "this page is irrelevant"
  but "I know what the numbers say, work on visibility anyway". Held for a
  month with a reason, so the record shows a human made the call and why.

Both are recorded rather than configured away: the record carries the
override and the exclusions, so a plan can always be read back as what the
engine said plus what a person changed.

Revision ID: 0048_client_overrides
Revises: 0047_organic_channel_rules
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0048_client_overrides"
down_revision = "0047_organic_channel_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "excluded_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        #: A normalized URL, or a path prefix ending in '*' for a section.
        sa.Column("url_pattern", sa.Text(), nullable=False),
        #: Why, in the words of whoever excluded it. Shown on the page, so a
        #: decision taken in March is legible in September.
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("client_id", "url_pattern", name="uq_excluded_pages_grain"),
    )
    op.create_index("ix_excluded_pages_client", "excluded_pages", ["client_id"])

    op.create_table(
        "constraint_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        #: "2026-10". One override per client per month: overriding is a
        #: decision about this month's plan, not a standing instruction.
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("constraint_name", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "client_id", "month", name="uq_constraint_overrides_grain"
        ),
    )
    op.create_check_constraint(
        "ck_constraint_overrides_name",
        "constraint_overrides",
        "constraint_name IN ('visibility', 'traffic', 'leads', "
        "'visibility_expansion')",
    )


def downgrade() -> None:
    op.drop_table("constraint_overrides")
    op.drop_index("ix_excluded_pages_client", table_name="excluded_pages")
    op.drop_table("excluded_pages")
