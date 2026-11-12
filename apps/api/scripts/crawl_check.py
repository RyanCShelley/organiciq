"""Crawl a few pages of a site with the real crawler and print what came back.

Run from apps/api:  .venv/bin/python scripts/crawl_check.py [domain] [page_limit]
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.crawler.fetch import crawl_site  # noqa: E402

DEFAULT_DOMAIN = "www." + "nashvillehomeorganizers" + ".com"


def main() -> None:
    domain = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DOMAIN
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    print(f"crawling {domain}, up to {limit} pages")
    # Every request with its time and answer, so a refusal can be placed in the sequence.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S", stream=sys.stdout)
    started = time.monotonic()
    result = asyncio.run(crawl_site(domain, page_limit=limit))
    for page in result.pages:
        what = page.parsed.title if page.parsed else page.fetch_error
        print(page.status_code, f"as_browser={page.read_as_browser}", what, page.normalized_url)
    print(
        f"pages: {len(result.pages)} | read as browser: {result.read_as_browser_pages}"
        f" | refused under both names: {result.refused_pages} | slowed: {result.throttled}"
        f" | took {time.monotonic() - started:.0f}s"
    )


if __name__ == "__main__":
    main()
