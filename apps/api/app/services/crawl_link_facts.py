"""What the site crawl knows about links to one page, for the diagnosis.

In-content links only: navigation and template links are on every page and say nothing
about this one. Returns None when the client has no crawl, so the caller can say it
could not check, rather than treat an unchecked page as having no links.
"""

from __future__ import annotations

from statistics import median
from typing import Any

from sqlalchemy.orm import Session

from app.core.urls import normalize_url
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlInternalLink, FactCrawlPageSnapshot
from app.services.target_signals import _latest_crawl_date


def link_facts(db: Session, client: Client, page_url: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """`{date, pages, inbound, median, linked_from, sources_without_link, sources_already_linking}`."""
    day = _latest_crawl_date(db, client.id)
    if day is None:
        return None

    snapshots = (
        db.query(FactCrawlPageSnapshot.normalized_url, FactCrawlPageSnapshot.inbound_editorial_links)
        .filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlPageSnapshot.snapshot_date == day,
        )
        .all()
    )
    if not snapshots:
        return None
    counts = {normalize_url(url): int(n or 0) for url, n in snapshots}
    target = normalize_url(page_url)

    linkers = {
        normalize_url(row.from_url)
        for row in db.query(FactCrawlInternalLink.from_url)
        .filter(
            FactCrawlInternalLink.client_id == client.id,
            FactCrawlInternalLink.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlInternalLink.snapshot_date == day,
            FactCrawlInternalLink.in_content.is_(True),
            FactCrawlInternalLink.is_template.is_(False),
        )
        .filter(FactCrawlInternalLink.to_url.in_([page_url, target]))
        .all()
    }

    without = [c for c in candidates if normalize_url(c["url"]) not in linkers]
    already = [c for c in candidates if normalize_url(c["url"]) in linkers]
    return {
        "date": day.isoformat(),
        "pages": len(counts),
        "in_crawl": target in counts,
        "inbound": counts.get(target, 0),
        "median": float(median(counts.values())) if counts else 0.0,
        "linked_from": sorted(linkers)[:5],
        "sources_without_link": without,
        "sources_already_linking": already,
    }
