"""Where a term belongs, proposed by meaning rather than by ranking.

The suggester reads Search Console: the page Google already shows for a
query. That is an observation and it is right where it exists — but it can
only ever propose a page that already ranks, so after a relaunch every
suggestion is the homepage, and a term that ranks nowhere gets nothing.

An embedding model proposes by subject instead. Measured against Search
Console on live data, it agreed on 72.2% of SMA's high-impression queries
against 32.8% for the token overlap the engine used, and the margin between
the best page and the runner-up is a strong confidence signal: at 0.10 it
proposed on a third of terms and was right 98.5% of the time.

Stored rather than computed on a page view: the model is a 159 MB dependency
and ~38 s per client, which is a monthly job and not a request.

Revision ID: 0054_keyword_page_suggestions
Revises: 0053_plan_overrides
"""

from alembic import op
import sqlalchemy as sa

revision = "0054_keyword_page_suggestions"
down_revision = "0053_plan_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "keyword_page_suggestions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id", sa.UUID(as_uuid=True), sa.ForeignKey("clients.id"), nullable=False
        ),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("page_url", sa.Text(), nullable=False),
        # Cosine similarity, and how far clear of the runner-up it was. The
        # margin is what decides whether this is shown at all.
        sa.Column("score", sa.Numeric(), nullable=False),
        sa.Column("margin", sa.Numeric(), nullable=False),
        # The runner-up, so a person can see what it was choosing between.
        sa.Column("runner_up_url", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("computed_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "keyword", name="uq_keyword_page_suggestion"),
    )
    op.create_index(
        "ix_keyword_page_suggestions_client", "keyword_page_suggestions", ["client_id"]
    )
    # The margin that earns a proposal for this client, calibrated against
    # its own Search Console pairs. A single global number would be too
    # loose for a site of near-identical pages and too tight for a varied
    # one: SMA's pages sit 0.398 apart on average, Element 6's 0.594.
    op.add_column(
        "clients", sa.Column("keyword_match_margin", sa.Numeric(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("clients", "keyword_match_margin")
    op.drop_index("ix_keyword_page_suggestions_client", table_name="keyword_page_suggestions")
    op.drop_table("keyword_page_suggestions")
