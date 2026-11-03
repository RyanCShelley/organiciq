"""Inlink suggester: which page should link to which, with the anchor text to use.

It joins what the site crawl knows (every internal link, so what already links where) with what Search Console knows (what each page
ranks for and earns) and with how alike two pages are in meaning (MiniLM text vectors of title and headings, as the keyword matcher
uses). The suggestion and anchor logic follows the Topic Hub tool: a source page that is similar to the target and does not link to it
yet, with a varied, descriptive anchor (`app.inlink_tools.anchors`, ported unchanged).

A target is a page that deserves more links: it earns or could earn search traffic and has few editorial links, or has none. A source is
a page that can lend: it earns clicks or has links of its own, has real content, and does not already link to the target.
"""

from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

from lxml import html as lxml_html
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions import visibility_candidates as vc
from app.inlink_tools.anchors import annotate_suggestions
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlInternalLink, FactCrawlPageSnapshot
from app.models.gsc import FactGscQueryPage
from app.models.schema_tools import InlinkState
from app.services import keyword_matcher
from app.services.page_diagnostic import read_page
from app.services.site_health import is_pagination

logger = logging.getLogger("organiciq.inlinks")

#: A page with fewer editorial links than this is under-linked.
WANTED_LINKS = 5
#: Topic Hub uses 0.35 but only within a topic cluster; without clusters a higher bar keeps the weak matches off the list.
MIN_SIMILARITY = 0.45
PER_TARGET = 5
TARGETS_SHOWN = 60
MAX_SOURCES = 400
MIN_WORDS = 100
MAX_OUTBOUND = 120
WINDOW_DAYS = 90
TOP_QUERIES = 4

_UTILITY = re.compile(r"(^|/)(cart|checkout|account|login|log-in|register|search|wishlist|password|thank-?you|order-status|404|sitemap|privacy|terms|policy|policies|shipping|returns?|refunds?)(/|$|-)", re.I)

_VECTORS: dict[tuple, Any] = {}


def is_utility(url: str) -> bool:
    return bool(_UTILITY.search(urlsplit(url).path))


def _vectors(db: Session, client: Client, pages: list[FactCrawlPageSnapshot]) -> dict[str, Any]:
    """Text vectors for the pages, kept for the life of the process per client and crawl (the pages change only when the site is crawled again)."""
    key = (str(client.id), max(p.snapshot_date for p in pages), len(pages))
    if key not in _VECTORS:
        if len(_VECTORS) > 4:
            _VECTORS.clear()
        matrix = keyword_matcher.embed_pages(pages)
        _VECTORS[key] = {p.normalized_url: matrix[i] for i, p in enumerate(pages)}
    return _VECTORS[key]


def _gsc(db: Session, client: Client, brand: list[str]) -> tuple[dict[str, dict[str, float]], dict[str, list[tuple[str, float]]]]:
    """Per page over the last 90 days: impressions, clicks and best position; and the searches (not brand) it earns the most impressions for."""
    newest = db.query(func.max(FactGscQueryPage.date)).filter(FactGscQueryPage.client_id == client.id).scalar()
    if newest is None:
        return {}, {}
    start = newest - timedelta(days=WINDOW_DAYS)
    q = func.lower(func.trim(FactGscQueryPage.query))
    rows = (
        db.query(q, FactGscQueryPage.normalized_url, func.sum(FactGscQueryPage.impressions), func.sum(FactGscQueryPage.clicks), func.sum(FactGscQueryPage.average_position * FactGscQueryPage.impressions))
        .filter(FactGscQueryPage.client_id == client.id, FactGscQueryPage.date > start)
        .group_by(q, FactGscQueryPage.normalized_url)
        .all()
    )
    pages: dict[str, dict[str, float]] = defaultdict(lambda: {"impressions": 0.0, "clicks": 0.0, "position": 999.0})
    queries: dict[str, list[tuple[str, float, float, float]]] = defaultdict(list)
    for query, url, imp, clk, weighted in rows:
        imp, clk = float(imp or 0), float(clk or 0)
        if imp <= 0 or vc.is_brand(query, brand):
            continue
        pos = float(weighted or 0) / imp
        p = pages[url]
        p["impressions"] += imp
        p["clicks"] += clk
        p["position"] = min(p["position"], pos)
        queries[url].append((query, imp, clk, pos))
    top = {u: [(q, i) for q, i, _c, _p in sorted(rows_, key=lambda r: -r[1])[:TOP_QUERIES]] for u, rows_ in queries.items()}
    return dict(pages), top


def _page_name(title: str | None, client: Client) -> str:
    """What the page is called, for anchor text: the title without a trailing brand segment ("ZOEY NATURALS | BUBBLE BATHS – Brand" is "Zoey Naturals Bubble Baths")."""
    parts = [p.strip() for p in re.split(r"\s+[|–—-]\s+", (title or "").strip()) if p.strip()]
    brandish = {re.sub(r"[^a-z0-9]", "", b) for b in vc.brand_keys(client)}
    if len(parts) > 1 and re.sub(r"[^a-z0-9]", "", parts[-1].lower()) in brandish:
        parts = parts[:-1]
    return " ".join(parts[:2]) if parts and re.sub(r"[^a-z0-9]", "", parts[0].lower()) not in brandish else ""


def _anchor_name(title: str | None, queries: list[tuple[str, float]] | None, client: Client) -> str:
    """What the page is called, for anchor text: its title before any separator, or, when that is only the brand, the search it earns most for."""
    name = _page_name(title, client)
    return name or (queries[0][0] if queries else (title or "")).strip()


def _doubled(anchor: str) -> bool:
    """"Brand's Brand": the same words twice around an apostrophe-s."""
    left, sep, right = anchor.partition("'s ")
    return bool(sep) and left.strip().lower() == right.strip().lower()


def _normalize(url: str) -> str:
    p = urlsplit(url)
    host = p.netloc.lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/') or '/'}" + (f"?{p.query}" if p.query else "")


def states(db: Session, client: Client) -> dict[str, Any]:
    ignored_pairs: set[tuple[str, str]] = set()
    ignored_targets: set[str] = set()
    live: set[tuple[str, str]] = set()
    rows = db.query(InlinkState).filter(InlinkState.client_id == client.id).all()
    for r in rows:
        if r.status == "ignored" and not r.source_url:
            ignored_targets.add(r.target_url)
        elif r.status == "ignored":
            ignored_pairs.add((r.source_url, r.target_url))
        elif r.status == "live":
            live.add((r.source_url, r.target_url))
    return {"pairs": ignored_pairs, "targets": ignored_targets, "live": live, "rows": rows}


def build(db: Session, client: Client) -> dict[str, Any] | None:
    pages = [p for p in keyword_matcher.crawled_pages(db, client) if p.status_code == 200 and not is_utility(p.normalized_url) and not is_pagination(p.normalized_url)]
    if len(pages) < 3:
        return None
    # A page whose canonical address is another page (Shopify's /collections/x/products/y is /products/y) is a duplicate: it is neither a
    # source nor a target, and a link to it counts as a link to the real page.
    canon: dict[str, str] = {}
    for p in pages:
        c = (p.canonical_url or "").strip()
        if c and _normalize(c) != _normalize(p.normalized_url):
            canon[p.normalized_url] = next((q.normalized_url for q in pages if _normalize(q.normalized_url) == _normalize(c)), "")
    duplicates = {u for u, c in canon.items() if c}
    pages = [p for p in pages if p.normalized_url not in duplicates]
    by_url = {p.normalized_url: p for p in pages}
    brand = vc.brand_keys(client)
    gsc, top_queries = _gsc(db, client, brand)

    edges = db.query(FactCrawlInternalLink.from_url, FactCrawlInternalLink.to_url, FactCrawlInternalLink.is_template).filter(
        FactCrawlInternalLink.client_id == client.id, FactCrawlInternalLink.source == CRAWL_SOURCE_FIRST_PARTY).all()
    linked: set[tuple[str, str]] = set()
    editorial_in: dict[str, set[str]] = defaultdict(set)
    outbound: dict[str, set[str]] = defaultdict(set)
    for a, b, template in edges:
        b = canon.get(b) or b
        a = canon.get(a) or a
        if a == b:
            continue
        linked.add((a, b))
        outbound[a].add(b)
        if not template:
            editorial_in[b].add(a)

    st = states(db, client)
    max_clicks = max((g["clicks"] for g in gsc.values()), default=0.0)

    # Targets: pages that deserve more links, most worth fixing first.
    targets = []
    for url, p in by_url.items():
        if url in st["targets"]:
            continue
        g = gsc.get(url)
        links = len(editorial_in.get(url, ()))
        deficit = max(0, WANTED_LINKS - links)
        if deficit == 0 or (g is None and links > 0):
            continue
        demand = math.log1p(g["impressions"]) * (1.5 if g and 4 <= g["position"] <= 20 else 1.0) if g else 0.0
        targets.append({"url": url, "page": p, "gsc": g, "links": links, "deficit": deficit, "need": round((1 + demand) * deficit, 2)})
    targets.sort(key=lambda t: -t["need"])
    targets = targets[:TARGETS_SHOWN]

    # Sources: pages with something to lend.
    def authority(url: str) -> float:
        g = gsc.get(url)
        return (g["clicks"] if g else 0.0) + 0.5 * len(editorial_in.get(url, ()))

    sources = [
        url for url, p in by_url.items()
        if (p.word_count or 0) >= MIN_WORDS and len(outbound.get(url, ())) < MAX_OUTBOUND and authority(url) > 0
    ]
    sources.sort(key=lambda u: -authority(u))
    sources = sources[:MAX_SOURCES]
    needed = {t["url"] for t in targets} | set(sources)
    vectors = _vectors(db, client, [by_url[u] for u in needed if u in by_url]) if targets and sources else {}

    recommendations = []
    total = 0
    for t in targets:
        url, tv = t["url"], vectors.get(t["url"])
        if tv is None:
            continue
        target_queries = {q for q, _ in top_queries.get(url, [])}
        scored = []
        for s in sources:
            if s == url or (s, url) in linked or (s, url) in st["pairs"] or (s, url) in st["live"] or s not in vectors:
                continue
            sim = float(tv @ vectors[s])
            shared = [q for q, _ in top_queries.get(s, []) if q in target_queries]
            if sim < MIN_SIMILARITY and not shared:
                continue
            sg, tg = gsc.get(s), t["gsc"]
            stronger = bool(shared and sg and sg["clicks"] >= 2 * ((tg or {"clicks": 0})["clicks"]))
            auth = math.log1p(authority(s)) / math.log1p(max_clicks + 1) if max_clicks else 0.0
            score = 0.65 * max(sim, 0.0) + (0.2 if stronger else 0.1 if shared else 0.0) + 0.15 * min(auth, 1.0)
            reasons = [f"Similar subject ({round(sim * 100)}% alike)"]
            if shared:
                reasons.insert(0, f"Both rank for “{shared[0]}”")
            if sg and sg["clicks"] >= 1:
                reasons.append(f"Earns {round(sg['clicks'])} clicks, so it has authority to pass on")
            scored.append((score, s, sim, reasons, sg))
        if not scored:
            continue
        scored.sort(key=lambda r: -r[0])
        picks = scored[:PER_TARGET]
        total += len(picks)
        p, g = t["page"], t["gsc"]
        recommendations.append(
            {
                "target_url": url, "target_title": _anchor_name(p.title, top_queries.get(url), client) or url, "title": p.title or url, "target_hub": url,
                "inbound": t["links"], "wanted": WANTED_LINKS, "need": t["need"],
                "impressions": round(g["impressions"]) if g else 0, "clicks": round(g["clicks"]) if g else 0, "position": round(g["position"], 1) if g and g["position"] < 999 else None,
                "queries": [q for q, _ in top_queries.get(url, [])],
                "suggestions": [
                    {"source_url": s, "source_title": by_url[s].title or s, "similarity": round(sim, 3), "score": round(score, 3), "reasons": reasons, "source_clicks": round(sg["clicks"]) if sg else 0}
                    for score, s, sim, reasons, sg in picks
                ],
            }
        )
    # Varied anchor text, Topic Hub's way: one set of candidates per target, rotated so no source links out with the same phrase twice.
    annotate_suggestions(recommendations, {r["target_url"]: r["queries"] for r in recommendations}, {})
    for r in recommendations:
        partial = (r.get("anchor_candidates") or {}).get("partial_match") or []
        for sug in r["suggestions"]:
            # A bare address is not an anchor to recommend, and "Brand's Brand" says nothing: fall back to the best descriptive phrase.
            if partial and (sug["suggested_anchor"].lower().startswith("http") or sug["anchor_type"] == "naked_url" or _doubled(sug["suggested_anchor"])):
                sug["suggested_anchor"], sug["anchor_type"] = partial[0], "partial_match"
            sug["anchor_alternates"] = [a for a in sug["anchor_alternates"] if a["type"] != "naked_url" and not a["anchor"].lower().startswith("http")]
        r.pop("target_hub", None)
        r.pop("anchor_candidates", None)

    ignored = [{"id": str(r.id), "target": r.target_url, "source": r.source_url or None, "status": r.status} for r in st["rows"] if r.status == "ignored"]
    return {
        "crawl_date": max(p.snapshot_date for p in pages).isoformat(), "pages": len(pages),
        "summary": {"targets": len(recommendations), "suggestions": total, "orphans": sum(1 for t in targets if t["links"] == 0), "live": len(st["live"]), "ignored": len(ignored)},
        "targets": recommendations, "ignored": ignored,
        "rule": f"A page is under-linked with fewer than {WANTED_LINKS} editorial links (links in the page's own content, not the menu or footer). A source must be at least {round(MIN_SIMILARITY * 100)}% alike in subject or rank for the same search, earn clicks or have links of its own, and not already link to the target.",
    }


# ── is the link live? ────────────────────────────────────────────────────────


def find_link(body: str, page_url: str, target_url: str) -> dict[str, Any]:
    """Whether the page links to the target, and the anchor text it uses (the Topic Hub tool's check, tolerant of www, trailing slash and http)."""
    want = _normalize(target_url)
    try:
        doc = lxml_html.fromstring(body)
    except Exception:  # noqa: BLE001
        return {"found": False, "anchor": None, "links": 0}
    count = 0
    for a in doc.xpath("//a[@href]"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        count += 1
        if _normalize(urljoin(page_url, href).split("#")[0]) == want:
            return {"found": True, "anchor": " ".join((a.text_content() or "").split())[:200] or None, "links": count}
    return {"found": False, "anchor": None, "links": count}


def verify(db: Session, client: Client, source: str, target: str, who: str) -> dict[str, Any]:
    found = read_page(source, client.domain)
    if not 200 <= found.status < 300:
        return {"found": False, "checked": False, "error": f"The page answered with status {found.status}, so it could not be checked."}
    result = find_link(found.body, found.final_url, target)
    if result["found"]:
        row = db.query(InlinkState).filter(InlinkState.client_id == client.id, InlinkState.source_url == source, InlinkState.target_url == target).one_or_none()
        if row is None:
            row = InlinkState(client_id=client.id, source_url=source, target_url=target, status="live", created_by=who)
            db.add(row)
        row.status, row.anchor, row.checked_at = "live", result["anchor"], datetime.now(timezone.utc)
        db.commit()
    return {**result, "checked": True, "error": None}
