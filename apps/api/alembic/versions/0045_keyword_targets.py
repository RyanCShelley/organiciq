"""keyword_page_map becomes keyword_targets: role, group and priority.

The spec's Decision 2 scores a keyword-page pair as a product, so a zero on
any factor removes the candidate. Two of its five factors are blocked on
this table:

* `fit` — 1.0 when the ranking URL is the mapped target, 0.5 when another
  URL ranks, 0.7 when there is no mapping yet. It needs a declared target.
* `w_group` — 1.5 for a priority group, 1.0 for other tracked groups.
  Every one of the 769 tracked keywords carries a `group_name` from SE
  Ranking, and nothing anywhere marks a group as the priority one.

V1 reads "priority-group keywords", V4 reads pages with a declared target,
and V-6 exists to raise a ticket when a term ranks on a URL that is not its
target. None of them can run without this.

Renamed rather than rebuilt. The table holds two rows, both SMA's, so the
data is not the point — the admin screen and the term-to-page suggester
already built against it are, and filling ten priority terms each across
twenty-four clients is the work this has to make bearable.

`role` and `priority` are nullable: a mapping somebody has made but not yet
ranked is a different statement from one nobody has looked at, and the
engine must be able to tell them apart rather than defaulting a judgement
nobody made.

Revision ID: 0045_keyword_targets
Revises: 0044_crawl_sections_and_faq
"""

from alembic import op
import sqlalchemy as sa

revision = "0045_keyword_targets"
down_revision = "0044_crawl_sections_and_faq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("keyword_page_map", "keyword_targets")
    # The spec calls it target_url, and "the page this term is for" is a
    # clearer thing than "the page it maps to".
    op.alter_column("keyword_targets", "page_url", new_column_name="target_url")

    op.add_column(
        "keyword_targets",
        sa.Column("term_role", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "keyword_targets",
        sa.Column("group_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "keyword_targets",
        sa.Column("priority", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Where the row came from. The engine reads only what a person confirmed;
    # a suggestion from the embedding matcher is a proposal until someone
    # agrees with it.
    op.add_column(
        "keyword_targets",
        sa.Column(
            "source", sa.String(length=16), nullable=False, server_default="confirmed"
        ),
    )
    op.add_column(
        "keyword_targets",
        sa.Column("confidence", sa.Numeric(), nullable=True),
    )

    op.execute(
        "ALTER INDEX IF EXISTS ix_keyword_page_map_client "
        "RENAME TO ix_keyword_targets_client"
    )
    op.execute(
        "ALTER TABLE keyword_targets RENAME CONSTRAINT "
        "uq_keyword_page_map_grain TO uq_keyword_targets_grain"
    )
    op.create_index(
        "ix_keyword_targets_priority",
        "keyword_targets",
        ["client_id", "priority"],
    )
    op.create_check_constraint(
        "ck_keyword_targets_term_role",
        "keyword_targets",
        "term_role IS NULL OR term_role IN ('primary', 'secondary')",
    )
    op.create_check_constraint(
        "ck_keyword_targets_source",
        "keyword_targets",
        "source IN ('confirmed', 'suggested')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_keyword_targets_source", "keyword_targets")
    op.drop_constraint("ck_keyword_targets_term_role", "keyword_targets")
    op.drop_index("ix_keyword_targets_priority", table_name="keyword_targets")
    op.execute(
        "ALTER TABLE keyword_targets RENAME CONSTRAINT "
        "uq_keyword_targets_grain TO uq_keyword_page_map_grain"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_keyword_targets_client "
        "RENAME TO ix_keyword_page_map_client"
    )
    for column in ("confidence", "source", "priority", "group_name", "term_role"):
        op.drop_column("keyword_targets", column)
    op.alter_column("keyword_targets", "target_url", new_column_name="page_url")
    op.rename_table("keyword_targets", "keyword_page_map")
