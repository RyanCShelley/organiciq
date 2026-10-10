"""Where a landing page sits in the funnel.

L3 asks what share of managed sessions land on a top-of-funnel page with no
route onward. Two of its three inputs were already here — the internal-link
graph and the declared conversion pages — and the third was not: nothing
recorded which *landing* pages are top of funnel. `classify_page_url` would
guess it from the URL, which is the thing `client_conversion_pages` exists to
stop.

So the stage is declared, like the conversion pages are. A model proposes and
a person confirms: `suggested_stage` is what the model said, `stage` is what
somebody agreed to, and only a row with `confirmed_at` counts. Keeping both
means a disagreement stays visible instead of being overwritten.

Revision ID: 0050_client_page_stages
Revises: 0049_engine_action_provenance
"""

from alembic import op
import sqlalchemy as sa

revision = "0050_client_page_stages"
down_revision = "0049_engine_action_provenance"
branch_labels = None
depends_on = None

STAGES = "('tofu', 'mofu', 'bofu')"


def upgrade() -> None:
    op.create_table(
        "client_page_stages",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        # What somebody agreed to. Null until they do.
        sa.Column("stage", sa.String(length=8), nullable=True),
        # What the model said, kept even after a person overrules it.
        sa.Column("suggested_stage", sa.String(length=8), nullable=True),
        sa.Column("confidence", sa.String(length=8), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("suggested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "normalized_url", name="uq_client_page_stage"),
        sa.CheckConstraint(f"stage IS NULL OR stage IN {STAGES}", name="ck_page_stage"),
        sa.CheckConstraint(
            f"suggested_stage IS NULL OR suggested_stage IN {STAGES}",
            name="ck_page_stage_suggested",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence IN ('high', 'medium', 'low')",
            name="ck_page_stage_confidence",
        ),
        # A confirmed row has to say what it was confirmed as.
        sa.CheckConstraint(
            "confirmed_at IS NULL OR stage IS NOT NULL",
            name="ck_page_stage_confirmed_has_stage",
        ),
    )
    op.create_index(
        "ix_client_page_stages_client", "client_page_stages", ["client_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_client_page_stages_client", table_name="client_page_stages")
    op.drop_table("client_page_stages")
