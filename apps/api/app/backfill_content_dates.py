"""Read freshness out of structured data we already hold.

The crawler now records when a page says it was last updated, but it only
does so on the next crawl, and the whole JSON-LD document has been stored
per page for months. For every client with schema on their pages, the
answer is already in the warehouse.

Sources 2 and 3 of the ladder — the `article:modified_time` meta and the
sitemap's `<lastmod>` — need the page fetched again, so they arrive with
the next crawl. This fills in what does not.

    python -m app.backfill_content_dates                    # dry run
    python -m app.backfill_content_dates --client acctek --apply
"""

from __future__ import annotations

import argparse

from app.core.db import SessionLocal
from app.ingestion.crawler.parse import newest_schema_date
from app.models.client import Client
from app.models.crawl import FactCrawlPageSchema, FactCrawlPageSnapshot


def backfill(db, client: Client, *, apply: bool) -> dict[str, int]:
    raws: dict[str, list[object]] = {}
    for url, raw in (
        db.query(FactCrawlPageSchema.normalized_url, FactCrawlPageSchema.raw).filter(
            FactCrawlPageSchema.client_id == client.id
        )
    ):
        if url and raw is not None:
            raws.setdefault(url, []).append(raw)

    pages = (
        db.query(FactCrawlPageSnapshot)
        .filter(FactCrawlPageSnapshot.client_id == client.id)
        .all()
    )
    dated = 0
    for page in pages:
        # Never overwrite what the crawl itself found: a date read from the
        # page beats one reconstructed here, and after the next crawl this
        # command should change nothing.
        if page.content_updated_on is not None:
            continue
        found = newest_schema_date(raws.get(page.normalized_url, []))
        if found is None:
            continue
        dated += 1
        if apply:
            page.content_updated_on = found
            page.content_updated_source = "schema"
    if apply:
        db.commit()
    return {"pages": len(pages), "dated": dated}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", help="One client's slug. Default: all of them.")
    parser.add_argument(
        "--apply", action="store_true", help="Write. Without it, nothing is saved."
    )
    args = parser.parse_args()

    db = SessionLocal()
    query = db.query(Client)
    if args.client:
        query = query.filter(Client.slug == args.client)
    for client in query.order_by(Client.slug).all():
        found = backfill(db, client, apply=args.apply)
        if not found["pages"]:
            continue
        share = found["dated"] / found["pages"] * 100
        print(
            f"{client.slug}: dated {found['dated']} of {found['pages']} "
            f"crawled pages from stored schema ({share:.0f}%)"
        )
    if not args.apply:
        print("\ndry run — nothing written. Add --apply.")


if __name__ == "__main__":
    main()
