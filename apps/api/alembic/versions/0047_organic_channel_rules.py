"""Any search engine is organic search, not "other".

The rules matched `google/organic` and `bing/organic` by name, so every other
search engine fell through to Other: 146 sessions from Yahoo and 97 from
DuckDuckGo in a single month, sitting in the bucket the engine ignores. Google
Business Profile traffic landed there too, which is the local SEO work being
counted as somebody else's.

Three rules, all of them matching on medium rather than naming engines, so
the next search engine does not need a release.

The existing facts carry the channel they were classified with at ingestion,
so the rows already mislabelled are reclassified here. A rule change that
only affects future syncs would leave the engine reading two different
definitions of organic depending on when a row arrived.

Revision ID: 0047_organic_channel_rules
Revises: 0046_monthly_records
"""

from alembic import op
import sqlalchemy as sa

revision = "0047_organic_channel_rules"
down_revision = "0046_monthly_records"
branch_labels = None
depends_on = None

#: Priority sits after the named engines so an explicit rule still wins.
NEW_RULES = (
    (25, None, "organic", None, "organic_search",
     "Any search engine reporting medium=organic. Yahoo, DuckDuckGo, Ecosia "
     "and whatever comes next, without naming them one at a time."),
    (26, "gmb", None, None, "organic_search",
     "Google Business Profile. Local SEO work, not an unclassified referral."),
    (27, None, "referral", None, "referral",
     "A real referral, so it stops hiding in Other alongside unattributable "
     "traffic. Whether referrals count toward a client's outcomes is a scope "
     "decision, and it cannot be made while they are invisible."),
)


def upgrade() -> None:
    for priority, source, medium, host, channel, description in NEW_RULES:
        op.execute(
            sa.text(
                """
                INSERT INTO channel_rules
                    (id, match_source, match_medium, match_host_contains,
                     channel, priority, active, description)
                SELECT gen_random_uuid(), :source, :medium, :host,
                       CAST(:channel AS organic_channel), :priority, true, :description
                WHERE NOT EXISTS (
                    SELECT 1 FROM channel_rules WHERE priority = :priority
                )
                """
            ).bindparams(
                source=source, medium=medium, host=host,
                channel=channel, priority=priority, description=description,
            )
        )

    # Reclassify what the missing rules mislabelled. Scoped to rows currently
    # in `other`, so nothing already classified is disturbed.
    for table in ("facts_ga4_traffic", "facts_ga4_events"):
        op.execute(
            sa.text(
                f"""
                UPDATE {table}
                   SET channel = 'organic_search'
                 WHERE channel = 'other'
                   AND lower(coalesce(session_medium, '')) = 'organic'
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                UPDATE {table}
                   SET channel = 'organic_search'
                 WHERE channel = 'other'
                   AND lower(coalesce(session_source, '')) = 'gmb'
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                UPDATE {table}
                   SET channel = 'referral'
                 WHERE channel = 'other'
                   AND lower(coalesce(session_medium, '')) = 'referral'
                """
            )
        )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM channel_rules WHERE priority IN (25, 26, 27)")
    )
