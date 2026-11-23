"""Shared FAQ page discovery and FQ-1 link suggestion helper."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.urls import normalize_url, url_variants
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlInternalLink, FactCrawlPageSchema

FAQ_PAGE_RE = re.compile(
    r"(^|[/\-_])(faqs?|frequently[-_]asked[-_]questions|common[-_]questions|questions[-_]and[-_]answers)([/\-_.]|$)",
    re.I,
)
FAQ_TITLE_RE = re.compile(
    r"\b(faqs?|frequently asked questions|common questions|questions\s*(?:and|&)\s*answers)\b",
    re.I,
)
_HELP_CENTER_RE = re.compile(r"(^|[/\-_])(help[-_]center|support[-_]center)([/\-_.]|$)", re.I)


def faq_schema_urls(db: Session, client: Client) -> set[str]:
    """URLs in the first-party crawl that declare FAQPage structured data."""
    rows = (
        db.query(FactCrawlPageSchema.normalized_url)
        .filter(
            FactCrawlPageSchema.client_id == client.id,
            FactCrawlPageSchema.schema_type == "FAQPage",
        )
        .all()
    )
    return {u for (u,) in rows if u}


def find_faq_page(
    db: Session,
    client: Client,
    site: dict[str, str] | None,
    page: str,
    *,
    schema_urls: set[str] | None = None,
) -> dict[str, Any] | None:
    """Return `FQ-1` part dict if the site has an FAQ page not yet linked in-content from `page`."""
    if not site:
        return None
    page_norm = normalize_url(page) or page
    faq_schemas = schema_urls if schema_urls is not None else faq_schema_urls(db, client)
    schema_norm = {normalize_url(s) or s for s in faq_schemas}
    candidates: list[str] = []
    for u, title in site.items():
        u_norm = normalize_url(u) or u
        if u_norm == page_norm:
            continue
        path = urlsplit(u).path or "/"
        path_match = bool(FAQ_PAGE_RE.search(path))
        help_title_match = bool(_HELP_CENTER_RE.search(path) and FAQ_TITLE_RE.search(title or ""))
        has_schema = u in faq_schemas or u_norm in schema_norm
        if path_match or help_title_match or has_schema:
            candidates.append(u)
    if not candidates:
        return None
    candidates.sort(key=len)
    target = candidates[0]
    from_urls = url_variants(page) or [page]
    to_urls = url_variants(target) or [target]
    linked = (
        db.query(FactCrawlInternalLink.id)
        .filter(
            FactCrawlInternalLink.client_id == client.id,
            FactCrawlInternalLink.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlInternalLink.from_url.in_(from_urls),
            FactCrawlInternalLink.to_url.in_(to_urls),
            FactCrawlInternalLink.in_content.is_(True),
        )
        .first()
    )
    if linked:
        return None
    return {
        "id": "FQ-1",
        "name": "Link to the site's FAQ page",
        "core": False,
        "confirmed_by_rule": False,
        "title": "Link to the site's FAQ page",
        "why": (
            "The site has an FAQ page, and the crawl found no link to it in this page's content. "
            "Someone with a question this page does not answer has nowhere to go from here."
        ),
        "steps": [
            f"The FAQ page: {target}",
            "Link to it from this page's FAQ, or from the point where a reader is most likely to have a further question.",
            "Use link text that says what is there, such as “See all frequently asked questions”.",
        ],
        "evidence": [
            f"FAQ page in the site crawl: {target}",
            "No in-content link from this page to it in the crawl.",
        ],
        "needs_to_confirm": "Nothing more: the crawl has already checked.",
        "confidence": "unconfirmed",
        "action_type": "Improve internal linking",
        "benefit": "SEO",
        "benefit_why": "A link from a page on the topic helps both a reader and a search engine reach the questions answered elsewhere on the site.",
    }
