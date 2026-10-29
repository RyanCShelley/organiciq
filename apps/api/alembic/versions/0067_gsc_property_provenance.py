"""Preserve Search Console property provenance across a domain migration."""
from alembic import op
import sqlalchemy as sa

revision = "0067_gsc_property_provenance"
down_revision = "0066_ga4_lead_measurements"
branch_labels = None
depends_on = None

GRAINS = {
    "facts_gsc_daily": ("uq_facts_gsc_daily_grain", ["client_id", "date"]),
    "facts_gsc_pages": ("uq_facts_gsc_pages_grain", ["client_id", "date", "normalized_url", "country", "device"]),
    "facts_gsc_query_pages": ("uq_facts_gsc_query_pages_grain", ["client_id", "date", "query", "normalized_url", "country", "device"]),
}

def upgrade():
    for table, (constraint, columns) in GRAINS.items():
        op.add_column(table, sa.Column("gsc_site_url", sa.String(512), nullable=False, server_default=""))
        op.drop_constraint(constraint, table, type_="unique")
        op.create_unique_constraint(constraint, table, [*columns, "gsc_site_url"])

def downgrade():
    for table, (constraint, columns) in GRAINS.items():
        # Postgres refuses this constraint if source rows overlap; no data is discarded.
        op.drop_constraint(constraint, table, type_="unique")
        op.create_unique_constraint(constraint, table, columns)
        op.drop_column(table, "gsc_site_url")
