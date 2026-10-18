"""Distinguish automatic page ownership from explicit user overrides."""
from alembic import op

revision = "0065_automatic_keyword_map"
down_revision = "0064_watch_targets"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_keyword_targets_source", "keyword_targets", type_="check")
    op.create_check_constraint("ck_keyword_targets_source", "keyword_targets", "source IN ('confirmed', 'suggested', 'auto')")


def downgrade():
    op.execute("UPDATE keyword_targets SET source = 'suggested' WHERE source = 'auto'")
    op.drop_constraint("ck_keyword_targets_source", "keyword_targets", type_="check")
    op.create_check_constraint("ck_keyword_targets_source", "keyword_targets", "source IN ('confirmed', 'suggested')")
