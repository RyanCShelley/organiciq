"""Move one client's stored URLs from an old host to a new one.

`client.domain` drives GA4 landing-page normalization and GSC URL rewriting, so
a stale domain quietly normalizes years of facts onto a host the site no longer
serves. The crawler, which follows redirects, writes the real one — and the two
stop joining.

SMA is the case this was written for: the record still said smamarketing.net
after the move to .com, and only 135 of 445 GSC URLs matched a crawled page, so
the Decision Engine's page-level levers were working on a third of the site
without anything looking wrong.

Usage, on the API service:

    # 1. See what would change
    python -m app.rehost_client_urls \\
        --client-id <uuid> --old-host smamarketing.net --new-host smamarketing.com

    # 2. Do it
    python -m app.rehost_client_urls \\
        --client-id <uuid> --old-host smamarketing.net --new-host smamarketing.com --apply

Dry run by default, and it reports collisions before touching anything. The care
is in those collisions: a page can already exist under both hosts at the same
grain, so a plain rewrite would violate the unique constraint. Colliding rows are
merged — counts summed, and `ctr` and `average_position` recomputed rather than
added, since adding a derived figure invents numbers.

`raw_url` is deliberately left alone: it records what the source actually
reported, and that is still true.

Safe to re-run: a second pass finds nothing on the old host.
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import text

from app.core.db import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("organiciq.rehost")

#: Impression-weighted. Every expression reads the pre-update row, so the old
#: impressions are still in scope while the weights are computed.
_GSC_MERGE = """
    average_position = case when (b.impressions + a.impressions) > 0
        then (b.average_position * b.impressions + a.average_position * a.impressions)
             / (b.impressions + a.impressions)
        else b.average_position end,
    ctr = case when (b.impressions + a.impressions) > 0
        then (b.clicks + a.clicks) / (b.impressions + a.impressions)
        else 0 end,
    impressions = b.impressions + a.impressions,
    clicks = b.clicks + a.clicks
"""

#: table -> (unique grain besides normalized_url, SET clause used when merging)
FACT_TABLES: dict[str, tuple[list[str], str]] = {
    "facts_gsc_pages": (["date", "country", "device"], _GSC_MERGE),
    "facts_gsc_query_pages": (["date", "query", "country", "device"], _GSC_MERGE),
    "facts_ga4_traffic": (
        ["date", "session_source", "session_medium", "channel"],
        """
        sessions = b.sessions + a.sessions,
        active_users = b.active_users + a.active_users,
        views = b.views + a.views,
        engaged_sessions = coalesce(b.engaged_sessions, 0) + coalesce(a.engaged_sessions, 0)
        """,
    ),
    "facts_ga4_events": (
        ["date", "session_source", "session_medium", "channel", "event_name"],
        "event_count = b.event_count + a.event_count",
    ),
}

#: Reference rows: a plain rewrite, nothing to merge.
REFERENCE_TABLES = ("annotations", "decisions")


def rehost_client_urls(
    db,
    *,
    client_id: str,
    old_host: str,
    new_host: str,
    apply: bool = False,
) -> dict[str, int]:
    """Rewrite one client's stored URLs. Returns counts; writes only when `apply`."""
    old = f"https://{old_host}"
    new = f"https://{new_host}"
    params = {"c": client_id, "old": f"{old}%", "oldp": old, "newp": new}

    rewritten = merged = 0

    for table, (grain, merge_set) in FACT_TABLES.items():
        on = " and ".join(f"a.{col} is not distinct from b.{col}" for col in grain)
        total = db.execute(
            text(f"select count(*) from {table} where client_id=:c and normalized_url like :old"),
            params,
        ).scalar()
        clash = db.execute(
            text(
                f"""
                select count(*) from {table} a
                join {table} b
                  on b.client_id = a.client_id
                 and b.normalized_url = replace(a.normalized_url, :oldp, :newp)
                 and {on}
                where a.client_id = :c and a.normalized_url like :old
                """
            ),
            params,
        ).scalar()
        logger.info("%-24s on old host: %6d  collides: %5d", table, total, clash)
        rewritten += total - clash
        merged += clash

        if not apply or not total:
            continue

        db.execute(
            text(
                f"""
                update {table} b set {merge_set}
                from {table} a
                where a.client_id = :c and a.normalized_url like :old
                  and b.client_id = a.client_id
                  and b.normalized_url = replace(a.normalized_url, :oldp, :newp)
                  and {on}
                """
            ),
            params,
        )
        db.execute(
            text(
                f"""
                delete from {table} a
                using {table} b
                where a.client_id = :c and a.normalized_url like :old
                  and b.client_id = a.client_id
                  and b.normalized_url = replace(a.normalized_url, :oldp, :newp)
                  and {on}
                """
            ),
            params,
        )
        db.execute(
            text(
                f"""
                update {table} set normalized_url = replace(normalized_url, :oldp, :newp)
                where client_id = :c and normalized_url like :old
                """
            ),
            params,
        )

    for table in REFERENCE_TABLES:
        total = db.execute(
            text(f"select count(*) from {table} where client_id=:c and page_url like :old"),
            params,
        ).scalar()
        logger.info("%-24s on old host: %6d", table, total)
        rewritten += total
        if apply and total:
            db.execute(
                text(
                    f"""
                    update {table} set page_url = replace(page_url, :oldp, :newp)
                    where client_id = :c and page_url like :old
                    """
                ),
                params,
            )

    if apply:
        db.execute(
            text("update clients set domain = :d where id = :c"),
            {"c": client_id, "d": new_host},
        )

    return {"rewritten": rewritten, "merged": merged}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--old-host", required=True, help="e.g. smamarketing.net")
    parser.add_argument("--new-host", required=True, help="e.g. smamarketing.com")
    parser.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        current = db.execute(
            text("select domain from clients where id = :c"), {"c": args.client_id}
        ).scalar()
        if current is None:
            logger.error("No client with id %s", args.client_id)
            return 1
        logger.info(
            "%s: %s -> %s (client.domain is %s)",
            "APPLY" if args.apply else "DRY RUN",
            args.old_host,
            args.new_host,
            current,
        )

        counts = rehost_client_urls(
            db,
            client_id=args.client_id,
            old_host=args.old_host,
            new_host=args.new_host,
            apply=args.apply,
        )

        if args.apply:
            db.commit()
            logger.info(
                "Rewritten %d, merged %d. client.domain is now %s.",
                counts["rewritten"],
                counts["merged"],
                args.new_host,
            )
            logger.info("Re-run the site crawl for this client to pick up the new host.")
        else:
            db.rollback()
            logger.info(
                "Would rewrite %d and merge %d. Re-run with --apply to write.",
                counts["rewritten"],
                counts["merged"],
            )
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
