"""Crawl one client's site and store it, exactly as the worker's crawl job does. For testing against a local database.

Run from apps/api, with DATABASE_URL pointing at the database to write to:

    DATABASE_URL=postgresql+psycopg://localhost/organiciq_local_test .venv/bin/python scripts/crawl_client.py absolutely-natural

The argument is the client's slug. It replaces that client's stored crawl, so do not point it at production.
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import SessionLocal  # noqa: E402
from app.ingestion.crawler.pipeline import run_site_crawl_job  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot  # noqa: E402
from app.models.job import SyncJob  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: crawl_client.py <client-slug>")
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s", datefmt="%H:%M:%S", stream=sys.stdout)
    db = SessionLocal()
    try:
        database = db.get_bind().url.database or ""
        # It replaces the stored crawl, so it only ever writes to a database that names itself as local or test.
        if "local" not in database and "test" not in database:
            sys.exit(f"refusing to write to {database!r}: this script is for a local test database (its name must contain 'local' or 'test')")
        client = db.query(Client).filter(Client.slug == sys.argv[1]).one_or_none()
        if client is None:
            sys.exit(f"no client with the slug {sys.argv[1]!r}; slugs here: {', '.join(s for (s,) in db.query(Client.slug))}")
        print(f"crawling {client.domain} into {database}")
        job = SyncJob(client_id=client.id, source="site_crawl", start_date=date.today(), end_date=date.today())
        db.add(job)
        db.commit()
        job = run_site_crawl_job(db, job)
        print(f"{job.status.value}: {job.error_message}")
        pages = db.query(FactCrawlPageSnapshot).filter(FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY).all()
        with_text = [p for p in pages if p.paragraphs]
        types: dict[str, int] = {}
        for p in pages:
            types[p.page_type or "none"] = types.get(p.page_type or "none", 0) + 1
        print(f"pages: {len(pages)} | with body paragraphs: {len(with_text)} | paragraphs kept: {sum(len(p.paragraphs) for p in with_text)}")
        print("page types: " + ", ".join(f"{k} {v}" for k, v in sorted(types.items(), key=lambda kv: -kv[1])))
    finally:
        db.close()


if __name__ == "__main__":
    main()
