"""Queue a sync job for one client, with history where the source has it.

The daily cycle pulls three days and the Integrations page offers ninety. Neither
reaches far enough to see a season: a pool leak detection company is quiet from
October to February, and you cannot measure that from a quarter of data.

Search Console serves about sixteen months, which is the most history available
and just enough to see one full year plus a little overlap. GA4 serves whatever
the property holds.

Usage, on the API service:

    # See the window that would be queued
    python -m app.backfill --client aquaman-leak-detection --source gsc_pages

    # Queue it
    python -m app.backfill --client aquaman-leak-detection --source gsc_pages --apply

Dry run by default. One job covers the whole window rather than a chunk per
month: only one job per client and source may be active at a time, so chunks
would have to be fed in one at a time by something that outlives this command.
The Search Console client pages through results, so a long window costs more
requests rather than failing.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from app.models.client import Client
from app.schemas import SyncJobCreate
from app.services.jobs import OverlappingJobError, enqueue_sync_job
from app.core.db import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("organiciq.backfill")

#: Search Console keeps about 16 months. Asking for more returns nothing extra.
MAX_MONTHS = {"gsc_pages": 16, "gsc_queries": 16}
#: Search Console finalises a day or two late; asking for today returns nothing.
SOURCE_LAG_DAYS = {"gsc_pages": 3, "gsc_queries": 3, "ga4": 2}

#: A crawl has no history to ask for — it reads the site as it is now — so it
#: takes a single-day window like the Run crawl button does. It lives here
#: because this is where one-off jobs are queued from a terminal, which is the
#: only route when the database is not reachable.
SAME_DAY_SOURCES = ("site_crawl",)

BACKFILLABLE = ("gsc_pages", "gsc_queries", "ga4", *SAME_DAY_SOURCES)


def backfill_window(source: str, months: int, today: date | None = None) -> tuple[date, date]:
    if source in SAME_DAY_SOURCES:
        day = today or date.today()
        return day, day
    end = (today or date.today()) - timedelta(days=SOURCE_LAG_DAYS.get(source, 2))
    capped = min(months, MAX_MONTHS.get(source, months))
    start = end - timedelta(days=round(capped * 365 / 12) - 1)
    return start, end


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True, help="client slug")
    parser.add_argument("--source", required=True, choices=BACKFILLABLE)
    parser.add_argument("--months", type=int, default=16)
    parser.add_argument("--apply", action="store_true", help="queue it; otherwise dry run")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.slug == args.client).one_or_none()
        if client is None:
            logger.error("No client with slug %r", args.client)
            return 1

        start, end = backfill_window(args.source, args.months)
        days = (end - start).days + 1
        capped = min(args.months, MAX_MONTHS.get(args.source, args.months))
        logger.info(
            "%s: %s / %s — %s to %s (%d days, %d months)",
            "APPLY" if args.apply else "DRY RUN",
            client.client_name,
            args.source,
            start,
            end,
            days,
            capped,
        )
        if args.source in SAME_DAY_SOURCES:
            logger.info("%s reads the site as it is now, so there is no window to widen.", args.source)
        elif capped < args.months:
            logger.info(
                "Capped at %d months: %s does not serve more than that.", capped, args.source
            )

        if not args.apply:
            logger.info("Re-run with --apply to queue it.")
            return 0

        try:
            job = enqueue_sync_job(
                db,
                client.id,
                SyncJobCreate(source=args.source, start_date=start, end_date=end),
            )
        except OverlappingJobError as exc:
            logger.error("%s", exc)
            logger.error("Wait for it to finish, or cancel it, then run this again.")
            return 1

        logger.info("Queued job %s. Watch it on the Sync jobs page.", job.id)
        logger.info("A window this long takes a while — it pages through Search Console.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
