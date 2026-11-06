"""When a host blocks our reader, read the page from the site crawl instead, and say so.

Some hosts (SiteGround's captcha is the usual one) answer our reader with a bot check instead of the page. The site crawl reached the page
another way and kept its title, description, headings with the first paragraph under each, the questions it answers, its markup and its
counts. This rebuilds a short page from that, so every rule that reads a page runs unchanged, and marks it as the crawl's so nothing
passes for a live read: every finding that stands on it says "from the crawl of <date>", and what is live now may differ.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx
from sqlalchemy.orm import Session

from app.core.urls import normalize_url
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSchema, FactCrawlPageSnapshot
from app.services import page_diagnostic
from app.services.page_diagnostic import Fetched, parse_page, unreadable_reason


def snapshot_for(db: Session, client: Client, url: str) -> FactCrawlPageSnapshot | None:
    return (
        db.query(FactCrawlPageSnapshot)
        .filter(FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot.normalized_url == normalize_url(url))
        .order_by(FactCrawlPageSnapshot.snapshot_date.desc())
        .first()
    )


def rebuild(db: Session, client: Client, snap: FactCrawlPageSnapshot, url: str, blocked: str) -> Fetched:
    """The page as the crawl held it, as HTML the usual parser reads."""
    head = [f"<title>{html.escape(snap.title or '')}</title>"]
    if snap.description:
        head.append(f'<meta name="description" content="{html.escape(snap.description, quote=True)}">')
    if snap.robots:
        head.append(f'<meta name="robots" content="{html.escape(snap.robots, quote=True)}">')
    if snap.canonical_url:
        head.append(f'<link rel="canonical" href="{html.escape(snap.canonical_url, quote=True)}">')
    for row in db.query(FactCrawlPageSchema).filter(FactCrawlPageSchema.client_id == client.id, FactCrawlPageSchema.normalized_url == snap.normalized_url, FactCrawlPageSchema.syntax == "json_ld"):
        if row.raw and not row.parse_error:
            head.append(f'<script type="application/ld+json">{json.dumps(row.raw)}</script>')
    body = []
    for sec in snap.sections or []:
        level = min(max(int(sec.get("level") or 2), 1), 6)
        if sec.get("heading"):
            body.append(f"<h{level}>{html.escape(str(sec['heading']))}</h{level}>")
        if sec.get("first_paragraph"):
            body.append(f"<p>{html.escape(str(sec['first_paragraph']))}</p>")
    day = snap.snapshot_date.strftime("%b %d, %Y")
    note = f"The site crawl of {day} (not a live read: {blocked[:1].lower() + blocked[1:].rstrip('.')}). It holds the page's title, description, headings with the first paragraph under each, questions and markup, so what is live now may differ"
    return Fetched(
        status=snap.status_code or 200, final_url=url, headers={}, body=f"<html><head>{''.join(head)}</head><body>{''.join(body)}</body></html>",
        requested_url=url, user_agent="", fetched_at=datetime.now(timezone.utc).isoformat(), size=0, source="crawl", source_note=note,
        word_count=snap.word_count, conversion_elements=snap.conversion_elements,
    )


def with_crawl(db: Session, client: Client, fetch: Callable[[str], Awaitable[Fetched]] | None = None) -> Callable[[str], Awaitable[Fetched]]:
    """A reader that tries the live page and, when the host answered with a bot check or nothing, returns the crawl's copy of it instead."""

    async def read(url: str) -> Fetched:
        try:
            live = await (fetch or page_diagnostic._fetch)(url)
        except httpx.HTTPError as exc:
            snap = snapshot_for(db, client, url)
            if snap is None or not (snap.title or snap.sections):
                raise
            return rebuild(db, client, snap, url, f"The page could not be fetched ({type(exc).__name__})")
        reason = unreadable_reason(live, parse_page(url=live.final_url, body=live.body, headers=live.headers))
        if reason is None:
            return live
        snap = snapshot_for(db, client, url)
        if snap is None or not (snap.title or snap.sections):
            return live
        return rebuild(db, client, snap, url, reason)

    return read
