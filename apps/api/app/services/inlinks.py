"""Inlink suggester: which page should link to which, from which paragraph, with the anchor text to use.

A link is suggested only between two pages that are about the same thing. That is measured, not assumed: each page has a
text vector built from its body paragraphs as well as its title and headings (MiniLM, as the keyword matcher uses), and a
source below the similarity floor is out whatever else is true of it. Two pages ranking for the same search is not a
reason on its own; it only adds to the score of a pair that is already alike.

The sources that pass are then put in order by where the link would go: the source's paragraph closest in meaning to the
target, and whether that paragraph already holds a phrase that would read as a natural anchor. Blog posts are preferred as
sources. Contact, about and utility pages never are. Each suggestion shows the paragraph and the anchor.

A customer review is never where a link goes: the site did not write it and cannot edit it. A page that is nothing but
reviews is therefore not a source.

The anchor is chosen by meaning, not by matching words: every short phrase in the paragraph is compared with what the target
is called (its name and the searches it ranks for) and the closest one is offered, under the anchor text rules in
`anchor_choices`.

How many links a page has decides only the order targets are shown in (pages with search demand and few links first). It
is never the reason a link is suggested.

Anchor variety follows the Topic Hub tool (`app.inlink_tools.anchors`, ported unchanged).
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

from app.decisions import action_context as ac
from app.decisions import visibility_candidates as vc
from app.ingestion.crawler.parse import review_heading
from app.inlink_tools.anchors import annotate_suggestions
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlInternalLink, FactCrawlPageSnapshot
from app.models.gsc import FactGscQueryPage
from app.models.schema_tools import InlinkState
from app.services import keyword_matcher, paragraph_vectors
from app.services.memo import Memo
from app.services.page_diagnostic import read_page
from app.services.site_health import is_pagination

logger = logging.getLogger("organiciq.inlinks")

#: A page with fewer editorial links than this is under-linked.
WANTED_LINKS = 5
#: The floor: a source less alike than this is never suggested. Topic Hub uses 0.35 but only within a topic cluster; without
#: clusters a higher bar keeps the weak matches off the list.
MIN_SIMILARITY = 0.50
#: How many of a target's most similar sources are looked at paragraph by paragraph.
RERANKED = 20
#: A paragraph this close to the source's best one is taken instead when it already holds a natural anchor.
PARAGRAPH_SLACK = 0.08
#: The anchor floor: a phrase in the paragraph less alike than this to what the target is called is not offered as the link.
ANCHOR_MIN = 0.70
#: An anchor is short: at most this many words, or one more when it is the target's own name or search word for word.
ANCHOR_WORDS = 4
#: How many of a target's best sources have their paragraphs read phrase by phrase for an anchor.
ANCHORED = 8
#: How much of a page's vector is its title and headings; the rest is its body paragraphs.
TITLE_WEIGHT = 0.35
#: A paragraph found on this many pages or more is the site's furniture (a shipping note, an ingredient glossary, a
#: reviews widget), not what any one page says. It is left out of a page's vector and is never where a link goes.
REPEATED_ON = 3
#: With at least this many pages, what every page of the site has in common is taken out of each page's vector before
#: two are compared. On a one-brand shop every page is "about" the brand, and without this any two pages look alike.
CENTRE_FROM = 30
#: Pages that are never a link source: nobody reads them for the subject.
NOT_SOURCES = frozenset({ac.ABOUT, ac.CONTACT, ac.UTILITY})
#: Pages preferred as sources: they are written to be read, and a link in a sentence belongs there.
PREFERRED_SOURCES = frozenset({ac.ARTICLE, ac.RESOURCE})
_STOP = frozenset("a an and are as at be best by for from how in is it of on or that the this to what which who why with your our my".split())
#: Words an anchor never starts or ends on: it would not stand on its own.
_EDGE = _STOP | frozenset("i we you they he she its their his her us them can will would should could may might do does did has have had was were been being also then than so if not no but into about after before when while just very more most some any all each every these those there here "
    # Everyday verbs: "sunscreen uses" and "matters when" are the middle of a sentence, not the name of anything.
    "use uses used using make makes made making help helps helped get gets got give gives keep keeps need needs work works apply applied contain contains include includes "
    "provide provides offer offers leave leaves feel feels matter matters go goes come comes take takes love loved want wants know knows say says said think".split())
#: Words that say nothing about where a link leads. A phrase made only of these ("read more", "this article") is never an anchor.
_GENERIC = frozenset("click here read more learn find out see check view visit shop buy now today article post page blog website site link info information details guide".split())
_JOINS = frozenset("of for with and in to on".split())
_BREAK = re.compile(r"[.,;:!?()\[\]\"“”|/•…]|\s[–—-]+\s")
_TOKEN = re.compile(r"\w[\w'’-]*")
PER_TARGET = 5
TARGETS_SHOWN = 60
MAX_SOURCES = 400
MIN_WORDS = 100
MAX_OUTBOUND = 120
WINDOW_DAYS = 90
TOP_QUERIES = 4

_UTILITY = re.compile(r"(^|/)(cart|checkout|account|login|log-in|register|search|wishlist|password|thank-?you|order-status|404|sitemap|privacy|terms|policy|policies|shipping|returns?|refunds?)(/|$|-)", re.I)

#: Page vectors, kept for the life of the process: one store per client and crawl, filled in as pages are needed.
_VECTORS: dict[tuple, dict[str, Any]] = {}
#: Whole results, kept until new Search Console data, a new crawl, or a change to what is ignored or confirmed.
_RESULTS = Memo(size=64, ttl=600.0)


def is_utility(url: str) -> bool:
    return bool(_UTILITY.search(urlsplit(url).path))


def _vectors(db: Session, client: Client, pages: list[FactCrawlPageSnapshot]) -> dict[str, Any]:
    """Text vectors for the pages, kept per client and crawl (the pages change only when the site is crawled again).

    Only the pages not yet held are worked out, so a different search or ignore list does not start from nothing.
    """
    if not pages:
        return {}
    key = (str(client.id), max(p.snapshot_date for p in pages))
    store = _VECTORS.get(key)
    if store is None:
        if len(_VECTORS) >= 8:
            _VECTORS.pop(next(iter(_VECTORS)))
        store = _VECTORS[key] = {}
    missing = [p for p in pages if p.normalized_url not in store]
    if missing:
        matrix = keyword_matcher.embed_pages(missing)
        store.update({p.normalized_url: matrix[i] for i, p in enumerate(missing)})
    return {p.normalized_url: store[p.normalized_url] for p in pages}


def page_type(p: FactCrawlPageSnapshot) -> str:
    """The page's type as the crawl recorded it, or worked out now for a crawl that predates it."""
    return p.page_type or ac.classify_page(p.normalized_url, title=p.title)["type"]


def _body_vectors(db: Session, client: Client, pages: list[FactCrawlPageSnapshot], title_vectors: dict[str, Any], embed=None) -> tuple[dict[str, Any], dict[str, Any]]:
    """`(page vectors, {url: (paragraph matrix, paragraph indexes)})`.

    A page's vector is its title-and-headings vector blended with the mean of its own paragraphs' vectors. A paragraph
    repeated across the site is not its own and is left out. A page whose crawl holds no paragraphs keeps its
    title-and-headings vector and has no matrix. With enough pages, what they all share is then subtracted.
    """
    import numpy as np

    seen_on: dict[str, int] = defaultdict(int)
    for p in pages:
        for h in {paragraph_vectors.text_hash(para.get("text") or "") for para in (p.paragraphs or [])}:
            seen_on[h] += 1
    own = {p.normalized_url: [(i, para["text"]) for i, para in enumerate(p.paragraphs or []) if para.get("text") and seen_on[paragraph_vectors.text_hash(para["text"])] < REPEATED_ON] for p in pages}
    held = paragraph_vectors.ensure(db, client.id, [t for rows in own.values() for _, t in rows], embed)
    vectors: dict[str, Any] = {}
    matrices: dict[str, Any] = {}
    for p in pages:
        title = title_vectors.get(p.normalized_url)
        if title is None:
            continue
        rows = [(i, held[paragraph_vectors.text_hash(t)]) for i, t in own[p.normalized_url] if paragraph_vectors.text_hash(t) in held]
        if not rows:
            vectors[p.normalized_url] = title
            continue
        matrix = np.vstack([v for _, v in rows])
        body = matrix.mean(axis=0)
        body = body / (np.linalg.norm(body) or 1.0)
        blended = TITLE_WEIGHT * title + (1 - TITLE_WEIGHT) * body
        vectors[p.normalized_url] = blended / (np.linalg.norm(blended) or 1.0)
        matrices[p.normalized_url] = (matrix, [i for i, _ in rows])
    if len(vectors) >= CENTRE_FROM:
        common = np.vstack(list(vectors.values())).mean(axis=0)
        for url, v in vectors.items():
            centred = v - common
            vectors[url] = centred / (np.linalg.norm(centred) or 1.0)
    return vectors, matrices


def _is_list(text: str) -> bool:
    words = len(text.split())
    return text.count(",") >= 6 and text.count(",") / max(words, 1) > 0.2


def _is_review(paragraph: dict[str, Any]) -> bool:
    """Whether a customer wrote the paragraph: the crawl marked it, or (for a crawl made before the mark) its heading says so."""
    return bool(paragraph.get("review")) or review_heading(paragraph.get("heading"))


def _only_reviews(page: FactCrawlPageSnapshot) -> bool:
    paragraphs = page.paragraphs or []
    return bool(paragraphs) and all(_is_review(x) for x in paragraphs)


def _key(text: str) -> str:
    return " ".join(_TOKEN.findall((text or "").lower().replace("-", " ").replace("’", "'")))


def _candidates(text: str, exact: set[str], digits: set[str], brand: list[str] | None, links: list[str] | None, own: str = "") -> list[tuple[int, str, str]]:
    """Every phrase in the paragraph that could be a link by the rules, as `(where it starts, as written, its words)`.

    Short (two to `ANCHOR_WORDS` words), inside one clause, not starting or ending on a filler word or holding a verb or
    pronoun, not a generic
    label, not the brand alone, not naming a number the target does not (an "SPF 50" is not a link to an SPF 30), not
    the name of the page it is on (`own`: "Mint Hand Soap" on the hand soap's page names that page, not another), and not
    inside or right beside words that are already a link.
    """
    own = f" {own} "
    brands = {_key(b) for b in brand or []}
    brand_words = {w for b in brands for w in b.split()}
    taken: list[tuple[int, int]] = []
    for link in links or []:
        for m in re.finditer(re.escape(link), text):
            taken.append((m.start() - 2, m.end() + 2))
    found: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    start = 0
    for cut in [*_BREAK.finditer(text), None]:
        end = cut.start() if cut else len(text)
        tokens = [(m.start() + start, m.end() + start, _key(m.group(0))) for m in _TOKEN.finditer(text[start:end])]
        for size in range(2, ANCHOR_WORDS + 2):
            for i in range(0, len(tokens) - size + 1):
                run = tokens[i : i + size]
                words = [w for _, _, k in run for w in k.split()]
                key = " ".join(words)
                if not words or words[0] in _EDGE or words[-1] in _EDGE or key in seen:
                    continue
                # "astringent and it's", "sunscreen I've": a contraction of a filler word, or any apostrophe at the end, is mid-sentence.
                if key not in exact and ("'" in words[-1] or any(w.split("'")[0] in _EDGE for w in words if "'" in w)):
                    continue
                if key not in exact and f" {key} " in own:
                    continue
                # "sunscreen is our strongest" is a piece of a sentence. Inside a name only a joining word belongs ("oil for hair").
                if key not in exact and any(w in _EDGE and w not in _JOINS for w in words[1:-1]):
                    continue
                if size > ANCHOR_WORDS and key not in exact:
                    continue
                meaning = [w for w in words if w not in _STOP]
                if len(meaning) < 2 and key not in exact:
                    continue
                if all(w in _GENERIC for w in meaning) or key in brands or all(w in brand_words for w in meaning):
                    continue
                if any(any(ch.isdigit() for ch in w) and w not in digits for w in words):
                    continue
                if any(run[0][0] < e and run[-1][1] > b for b, e in taken):
                    continue
                seen.add(key)
                found.append((run[0][0], text[run[0][0] : run[-1][1]], key))
        start = cut.end() if cut else end
    return found


def anchor_choices(text: str, phrases: list[str], vectors: Any, embed, brand: list[str] | None = None, links: list[str] | None = None, own: str = "") -> list[tuple[str, float]]:
    """The phrases already in the paragraph that would read as the link, best first, each with how alike it is to the target.

    `phrases` is what the target is called (its name and the searches it ranks for) and `vectors` their vectors, one row
    each; `embed` turns a list of phrases into vectors. A phrase is scored by meaning against the closest of them, on its
    own and out of its sentence, so it has to describe the target without the words around it. The target's name or search
    found word for word comes first. `own` is the name of the page the paragraph is on, which is never an anchor to
    another page. Returned as the paragraph writes it; empty when nothing clears `ANCHOR_MIN`.
    """
    exact = {k for k in (_key(x) for x in phrases) if k}
    target_words = {w for k in exact for w in k.split()}
    found = _candidates(text, exact, {w for w in target_words if any(ch.isdigit() for ch in w)}, brand, links, _key(own))
    if not found or vectors is None or not len(vectors):
        return []
    scored = []
    for (where, written, key), v in zip(found, embed([key for _, _, key in found])):
        score = float((vectors @ v).max())
        if key not in exact and score < ANCHOR_MIN:
            continue
        meaning = [w for w in key.split() if w not in _STOP]
        overlap = sum(1 for w in meaning if w in target_words) / max(len(meaning), 1)
        scored.append((key not in exact, -round(score, 2), -overlap, where, written, score))
    scored.sort()
    return [(written, round(score, 3)) for *_, written, score in scored]


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


#: What a person has done with one suggested link. "todo" is a link nothing was done with, kept only when its link text was chosen.
LINK_STATUSES = ("todo", "added", "live", "skipped")


def link_status(row: InlinkState | None) -> str:
    """A saved row's status as the screen names it. A pair ignored before statuses existed is a skipped link."""
    if row is None:
        return "todo"
    return "skipped" if row.status == "ignored" else row.status if row.status in LINK_STATUSES else "todo"


def states(db: Session, client: Client) -> dict[str, Any]:
    ignored_pairs: set[tuple[str, str]] = set()
    ignored_targets: set[str] = set()
    live: set[tuple[str, str]] = set()
    by_pair: dict[tuple[str, str], InlinkState] = {}
    rows = db.query(InlinkState).filter(InlinkState.client_id == client.id).all()
    for r in rows:
        if not r.source_url:
            if r.status == "ignored":
                ignored_targets.add(r.target_url)
            continue
        by_pair[(r.source_url, r.target_url)] = r
        if link_status(r) == "skipped":
            ignored_pairs.add((r.source_url, r.target_url))
        elif r.status == "live":
            live.add((r.source_url, r.target_url))
    return {"pairs": ignored_pairs, "targets": ignored_targets, "live": live, "rows": rows, "by_pair": by_pair}


def set_state(db: Session, client: Client, source: str, target: str, who: str, status: str | None = None, anchor: str | None = None) -> dict[str, Any]:
    """Save what a person did with one link (`status`) or the link text they chose (`anchor`); either may be left as it is.

    A link set back to "todo" with no chosen text has nothing left to remember, so its row goes.
    """
    row = db.query(InlinkState).filter(InlinkState.client_id == client.id, InlinkState.source_url == source, InlinkState.target_url == target).one_or_none()
    if row is None:
        row = InlinkState(client_id=client.id, source_url=source, target_url=target, status="todo", created_by=who)
        db.add(row)
    if status is not None:
        if link_status(row) == "live" and status != "live":
            row.anchor, row.checked_at = None, None
        row.status = status
    if anchor is not None:
        row.anchor = " ".join(anchor.split())[:300] or None
        # A sentence written around other words no longer carries this link.
        if row.sentence and (row.sentence_anchor or "").lower() != (row.anchor or "").lower():
            row.sentence, row.sentence_anchor = None, None
    if link_status(row) == "todo" and not row.anchor:
        db.delete(row)
        db.commit()
        return {"status": "todo", "anchor": None}
    db.commit()
    return {"status": link_status(row), "anchor": row.anchor}


def build(db: Session, client: Client, q: str | None = None) -> dict[str, Any] | None:
    """The suggestions, kept until the data they come from changes: a new crawl, newer Search Console data, or a link ignored or confirmed."""
    st = states(db, client)
    newest_crawl = db.query(func.max(FactCrawlPageSnapshot.snapshot_date)).filter(FactCrawlPageSnapshot.client_id == client.id).scalar()
    newest_gsc = db.query(func.max(FactGscQueryPage.date)).filter(FactGscQueryPage.client_id == client.id).scalar()
    key = (
        str(client.id), " ".join((q or "").lower().split()), newest_crawl, newest_gsc, tuple(vc.brand_keys(client)),
        hash(frozenset(st["pairs"])), hash(frozenset(st["targets"])), hash(frozenset(st["live"])),
        hash(frozenset((k, r.status, r.anchor, r.checked_at, r.sentence) for k, r in st["by_pair"].items())),
    )
    return _RESULTS.get(key, lambda: _build(db, client, q, st))


def _build(db: Session, client: Client, q: str | None, st: dict[str, Any]) -> dict[str, Any] | None:
    pages = [p for p in keyword_matcher.crawled_pages(db, client) if p.status_code == 200 and not is_utility(p.normalized_url) and not is_pagination(p.normalized_url)]
    if len(pages) < 3:
        return None
    # A page whose canonical address is another page (Shopify's /collections/x/products/y is /products/y) is a duplicate: it is neither a
    # source nor a target, and a link to it counts as a link to the real page.
    canon: dict[str, str] = {}
    by_normal: dict[str, str] = {}
    for p in pages:
        by_normal.setdefault(_normalize(p.normalized_url), p.normalized_url)
    for p in pages:
        c = (p.canonical_url or "").strip()
        if c and _normalize(c) != _normalize(p.normalized_url):
            canon[p.normalized_url] = by_normal.get(_normalize(c), "")
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

    max_clicks = max((g["clicks"] for g in gsc.values()), default=0.0)

    # Targets: pages that deserve more links, most worth fixing first.
    needle = " ".join((q or "").lower().split())
    targets = []
    for url, p in by_url.items():
        if url in st["targets"]:
            continue
        g = gsc.get(url)
        links = len(editorial_in.get(url, ()))
        deficit = max(0, WANTED_LINKS - links)
        if needle:
            # Looking for a page: it matches on its address, its title, or a search it ranks for, and is shown even when it already has enough links.
            if needle not in url.lower() and needle not in (p.title or "").lower() and not any(needle in qr for qr, _ in top_queries.get(url, [])):
                continue
        elif deficit == 0 or (g is None and links > 0):
            continue
        demand = math.log1p(g["impressions"]) * (1.5 if g and 4 <= g["position"] <= 20 else 1.0) if g else 0.0
        targets.append({"url": url, "page": p, "gsc": g, "links": links, "deficit": deficit, "need": round((1 + demand) * deficit, 2)})
    targets.sort(key=lambda t: -t["need"])
    targets = targets[: (TARGETS_SHOWN if not needle else 25)]

    # Sources: pages with something to lend.
    def authority(url: str) -> float:
        g = gsc.get(url)
        return (g["clicks"] if g else 0.0) + 0.5 * len(editorial_in.get(url, ()))

    types = {url: page_type(p) for url, p in by_url.items()}
    sources = [
        url for url, p in by_url.items()
        if (p.word_count or 0) >= MIN_WORDS and len(outbound.get(url, ())) < MAX_OUTBOUND and authority(url) > 0 and types[url] not in NOT_SOURCES
        # A page that is nothing but reviews has no sentence of the site's own for a link to go in.
        and not _only_reviews(p)
    ]
    sources.sort(key=lambda u: -authority(u))
    sources = sources[:MAX_SOURCES]
    needed = [by_url[u] for u in ({t["url"] for t in targets} | set(sources)) if u in by_url]
    title_vectors = _vectors(db, client, needed) if targets and sources else {}
    vectors, matrices = _body_vectors(db, client, needed, title_vectors) if title_vectors else ({}, {})
    with_body = sum(1 for s in sources if s in matrices)
    # What each target is about, in the words a link to it would use: its name and the searches it ranks for.
    described = [t for t in targets if t["url"] in vectors]
    names = {t["url"]: _anchor_name(t["page"].title, top_queries.get(t["url"]), client) for t in described}
    about = dict(zip(
        [t["url"] for t in described],
        keyword_matcher._embed([". ".join(x for x in [names[t["url"]], ", ".join(q for q, _ in top_queries.get(t["url"], []))] if x) or t["url"] for t in described]),
    )) if described else {}

    # Phrase vectors, worked out once each for this run: the same paragraphs are read for many targets.
    phrase_store: dict[str, Any] = {}

    def embed_phrases(texts: list[str]):
        import numpy as np

        missing = [t for t in dict.fromkeys(texts) if t not in phrase_store]
        if missing:
            phrase_store.update(zip(missing, keyword_matcher._embed(missing)))
        return np.vstack([phrase_store[t] for t in texts])

    recommendations = []
    total = 0
    for t in targets:
        url, tv = t["url"], vectors.get(t["url"])
        if tv is None:
            continue
        target_queries = {q for q, _ in top_queries.get(url, [])}
        alike = []
        for s in sources:
            if s == url or s not in vectors:
                continue
            # A link somebody has already acted on (added, confirmed live, skipped) stays on the page's list as it was left.
            acted = link_status(st["by_pair"].get((s, url))) != "todo"
            if (s, url) in linked and not acted:
                continue
            sim = float(tv @ vectors[s])
            # The hard requirement. A shared search does not let an unrelated page through; it only adds to the score below.
            if sim < MIN_SIMILARITY and not acted:
                continue
            alike.append((sim, s, acted))
        alike.sort(key=lambda r: -r[0])
        alike = [(sim, s) for sim, s, acted in alike if acted] + [(sim, s) for sim, s, acted in alike if not acted][:RERANKED]
        phrases = [x for x in [names.get(url, ""), *[q for q, _ in top_queries.get(url, [])]] if x and x.strip()]
        called = embed_phrases([_key(x) for x in phrases]) if phrases else None
        # First where the link would go in each source, then, for the best of them, the phrase in that paragraph to link from.
        placed = []
        for sim, s in alike:
            shared = [q for q, _ in top_queries.get(s, []) if q in target_queries]
            auth = math.log1p(authority(s)) / math.log1p(max_clicks + 1) if max_clicks else 0.0
            preferred = types[s] in PREFERRED_SOURCES
            paras = by_url[s].paragraphs or []
            order: list[int] = []
            closeness, where = None, []
            held = matrices.get(s)
            if held is not None:
                matrix, where = held
                closeness = matrix @ about[url]
                # A review is never where a link goes, whatever it says.
                own = [i for i in range(len(closeness)) if not _is_review(paras[where[i]])]
                # A run of ingredients or attributes separated by commas is a list, not a sentence a link can sit in.
                prose = [i for i in own if not _is_list(paras[where[i]]["text"])] or own
                order = sorted(prose, key=lambda i: -float(closeness[i]))[:3]
            par_sim = float(closeness[order[0]]) if order else 0.0
            before = 0.45 * sim + 0.25 * max(par_sim, 0.0) + (0.08 if preferred else 0.0) + (0.05 if shared else 0.0) + 0.05 * min(auth, 1.0)
            placed.append((before, s, sim, shared, preferred, order, closeness, where, paras))
        placed.sort(key=lambda r: -r[0])
        scored = []
        for rank, (before, s, sim, shared, preferred, order, closeness, where, paras) in enumerate(placed):
            sg = gsc.get(s)
            paragraph, choices, par_sim = None, [], 0.0
            if order:
                pick = order[0]
                if rank < ANCHORED and called is not None:
                    for i in order:
                        if float(closeness[order[0]]) - float(closeness[i]) > PARAGRAPH_SLACK:
                            continue
                        para = paras[where[i]]
                        found = anchor_choices(para["text"], phrases, called, embed_phrases, brand, para.get("links"), _page_name(by_url[s].title, client))
                        if found:
                            pick, choices = i, found
                            break
                paragraph, par_sim = paras[where[pick]], float(closeness[pick])
            score = before + 0.25 * (max(par_sim, 0.0) - max(float(closeness[order[0]]), 0.0) if order else 0.0) + (0.12 if choices else 0.0)
            reasons = [f"Similar subject ({round(sim * 100)}% alike)"]
            if paragraph and not choices:
                reasons.append("The closest paragraph has no phrase that reads as the link, so a sentence would need adding")
            if preferred:
                reasons.append(f"{ac.PAGE_NAMES[types[s]]}: written to be read")
            if shared:
                reasons.append(f"Both rank for “{shared[0]}”")
            if sg and sg["clicks"] >= 1:
                reasons.append(f"Earns {round(sg['clicks'])} clicks, so it has authority to pass on")
            scored.append([score, s, sim, reasons, sg, paragraph, choices, par_sim])
        if not scored:
            continue
        scored.sort(key=lambda r: -r[0])
        # Links already acted on are all kept. New ones fill what is left of the page's five; a skipped link does not use a place.
        status_of = {r[1]: link_status(st["by_pair"].get((r[1], url))) for r in scored}
        room = max(0, PER_TARGET - sum(1 for v in status_of.values() if v in ("added", "live")))
        fresh = [r[1] for r in scored if status_of[r[1]] == "todo"][:room]
        picks = [r for r in scored if status_of[r[1]] != "todo" or r[1] in fresh]
        total += sum(1 for r in picks if status_of[r[1]] == "todo")
        # No two links to one page carry the same words when the paragraph offers another phrase that also reads as the link.
        used: set[str] = set()
        for row in picks:
            choices = row[6]
            chosen = next((c for c in choices if c[0].lower() not in used), choices[0] if choices else None)
            if chosen:
                used.add(chosen[0].lower())
                row[3].insert(1, f"The paragraph already says “{chosen[0]}”")
            row[6] = chosen
        p, g = t["page"], t["gsc"]
        recommendations.append(
            {
                "target_url": url, "target_title": _anchor_name(p.title, top_queries.get(url), client) or url, "title": p.title or url, "target_hub": url,
                "target_type": ac.PAGE_NAMES[types[url]],
                "inbound": t["links"], "wanted": WANTED_LINKS, "need": t["need"],
                "impressions": round(g["impressions"]) if g else 0, "clicks": round(g["clicks"]) if g else 0, "position": round(g["position"], 1) if g and g["position"] < 999 else None,
                "queries": [q for q, _ in top_queries.get(url, [])],
                "suggestions": [
                    {
                        "source_url": s, "source_title": by_url[s].title or s, "source_type": ac.PAGE_NAMES[types[s]], "similarity": round(sim, 3), "score": round(score, 3),
                        "reasons": reasons, "source_clicks": round(sg["clicks"]) if sg else 0,
                        # Where the link goes: the source's paragraph closest to the target, and the phrase in it to link from, when there is one.
                        "paragraph": {"heading": paragraph.get("heading") or None, "text": paragraph["text"]} if paragraph else None,
                        "anchor_in_paragraph": anchor[0] if anchor else None, "anchor_similarity": anchor[1] if anchor else None,
                        "paragraph_similarity": round(par_sim, 3) if paragraph else None,
                        # What a person did with this link and the link text they chose. For a live link, the words found on the page.
                        "status": status_of[s],
                        "chosen_anchor": (st["by_pair"][(s, url)].anchor if status_of[s] != "live" else None) if (s, url) in st["by_pair"] else None,
                        "live_anchor": st["by_pair"][(s, url)].anchor if status_of[s] == "live" else None,
                        "checked_at": st["by_pair"][(s, url)].checked_at.isoformat() if status_of[s] == "live" and st["by_pair"][(s, url)].checked_at else None,
                        # The sentence written to carry this link, when one was asked for, and the link text it was written around.
                        "sentence": st["by_pair"][(s, url)].sentence if (s, url) in st["by_pair"] else None,
                        "sentence_anchor": st["by_pair"][(s, url)].sentence_anchor if (s, url) in st["by_pair"] else None,
                    }
                    for score, s, sim, reasons, sg, paragraph, anchor, par_sim in picks
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
            # A phrase the paragraph already uses is the anchor: nothing has to be written to make the link.
            if sug.get("anchor_in_paragraph"):
                sug["suggested_anchor"], sug["anchor_type"] = sug["anchor_in_paragraph"], "in_paragraph"
        r.pop("target_hub", None)
        r.pop("anchor_candidates", None)

    # Whole pages set aside. A single skipped link is shown on its page's own list, with its own Restore.
    ignored = [{"id": str(r.id), "target": r.target_url, "source": None, "status": r.status} for r in st["rows"] if r.status == "ignored" and not r.source_url]
    return {
        "q": needle or None, "crawl_date": max(p.snapshot_date for p in pages).isoformat(), "pages": len(pages),
        "summary": {"targets": len(recommendations), "suggestions": total, "orphans": sum(1 for t in targets if t["links"] == 0), "live": len(st["live"]), "ignored": len(ignored)},
        "targets": recommendations, "ignored": ignored,
        # Whether the comparison had body text to go on. A crawl made before paragraphs were kept has only titles and headings.
        "body_text": {"sources": len(sources), "with_paragraphs": with_body},
        # The two numbers the screen's short "how suggestions are picked" note quotes.
        "min_similarity": round(MIN_SIMILARITY * 100), "wanted_links": WANTED_LINKS,
        "rule": (
            f"A source must be at least {round(MIN_SIMILARITY * 100)}% alike in subject to the target, measured on the pages' body text as well as their titles and headings. "
            "Ranking for the same search adds to a pair's score but never qualifies it. Contact, about and utility pages are never sources, and blog posts are preferred. "
            "A customer review is never where a link goes. The anchor is a short phrase already in the paragraph, chosen for how closely it means what the target page is called; "
            "a brand name alone, a generic label such as “read more”, and words that are already a link are never used. "
            "A source must also earn clicks or have links of its own and not already link to the target. "
            f"Pages with search demand and fewer than {WANTED_LINKS} editorial links are listed first; the link count decides the order only."
            + ("" if with_body else " This crawl was made before body paragraphs were kept, so pages are compared on titles and headings only and no paragraph is shown. Crawl the site again to get them.")
        ),
    }


# ── the sentence to add ─────────────────────────────────────────────────────

#: A sentence added for a link is one sentence, and short.
SENTENCE_WORDS = 30

SENTENCE_PROMPT = """You are adding one internal link to a page of {site}. Write ONE sentence that will be added to the page directly after the paragraph below, and that contains the link.

The paragraph it follows (on the page "{source_title}"):
"{paragraph}"
{following}
The page being linked to: "{target_name}" ({target_type}). People find that page by searching: {queries}.

The link text, which must appear in your sentence exactly once and word for word: "{anchor}"

Rules:
- One sentence, at most {words} words, in plain English, in the same voice and person as the paragraph.
- It must read on naturally from the paragraph and give the reader a reason to follow the link.
- The link text must make sense in the sentence. Do not put "click here", "read more" or a web address around it.
- Do not state any number, price, percentage, ingredient, medical or health claim, or promise that is not in the paragraph above.
- Do not repeat what the paragraph already says. No exclamation marks, no emoji, no markup.
{again}
Return only JSON: {{"sentence": "..."}}"""

_HEALTH = re.compile(r"\b(cures?|treats?|heals?|prevents?|clinically|proven|guaranteed?|doctor[- ]recommended)\b", re.I)


def sentence_problem(sentence: str, anchor: str, allowed: str) -> str | None:
    """Why a written sentence cannot be used, or None when it can. `allowed` is the text any number or claim has to come from."""
    words = sentence.split()
    if not words:
        return "nothing was written"
    if len(re.findall(re.escape(anchor), sentence, re.I)) != 1:
        return f"the link text “{anchor}” has to appear exactly once"
    if len(words) > SENTENCE_WORDS:
        return f"it is {len(words)} words, and the limit is {SENTENCE_WORDS}"
    if re.search(r"[.!?]\s+\S", sentence.replace(anchor, "")) or not sentence.rstrip().endswith((".", "?")):
        return "it has to be one sentence, ending in a full stop"
    if re.search(r"https?://|www\.|<[a-z/]|\[[^\]]+\]\(|[*_#]{2}", sentence, re.I):
        return "it must not contain an address or any markup"
    held = allowed.lower()
    for number in re.findall(r"\d[\d.,%]*", sentence):
        if number.rstrip(".,") not in held:
            return f"it states “{number}”, which the paragraph does not"
    claim = _HEALTH.search(sentence)
    if claim and claim.group(0).lower() not in held:
        return f"it makes a claim (“{claim.group(0)}”) the paragraph does not"
    return None


def write_sentence(db: Session, client: Client, source: str, target: str, anchor: str, who: str, ask=None) -> dict[str, Any]:
    """Write the sentence that carries a suggested link, check it, and keep it on the link for everyone.

    The model writes; the checks in `sentence_problem` decide. A sentence that fails is asked for once more with the
    reason, and if it fails again nothing is saved and the reason is returned.
    """
    anchor = " ".join((anchor or "").split())
    data = build(db, client, None) or {}
    found = next(((t, k) for t in data.get("targets", []) for k in t["suggestions"] if t["target_url"] == target and k["source_url"] == source), None)
    if found is None:
        # A page looked up by search is not on the main list.
        data = build(db, client, urlsplit(target).path) or {}
        found = next(((t, k) for t in data.get("targets", []) for k in t["suggestions"] if t["target_url"] == target and k["source_url"] == source), None)
    if found is None:
        return {"ok": False, "reason": "That link is no longer suggested, so there is nothing to write a sentence for."}
    t, k = found
    if not k.get("paragraph"):
        return {"ok": False, "reason": "The crawl holds no paragraph of this page to write the sentence after. Crawl the site again."}
    if not anchor or all(w in _GENERIC or w in _STOP for w in _key(anchor).split()):
        return {"ok": False, "reason": "Choose a link text that says where the link leads first."}
    paragraph = k["paragraph"]["text"]
    page = next((p for p in keyword_matcher.crawled_pages(db, client) if p.normalized_url == source), None)
    texts = [x["text"] for x in (page.paragraphs or []) if not _is_review(x)] if page else []
    after = texts[texts.index(paragraph) + 1] if paragraph in texts and texts.index(paragraph) + 1 < len(texts) else ""
    if ask is None:
        from app.schema_tools import llm as model

        ask = lambda prompt: model.call("quick", prompt, max_tokens=400)[0]  # noqa: E731
    from app.schema_tools.llm import extract_json

    allowed = f"{paragraph} {t['target_title']} {anchor}"
    problem, sentence = None, ""
    for _attempt in range(2):
        prompt = SENTENCE_PROMPT.format(
            site=client.domain, source_title=k["source_title"], paragraph=paragraph[:1200],
            following=f'The paragraph that comes after it (your sentence goes between the two):\n"{after[:600]}"\n' if after else "",
            target_name=t["target_title"], target_type=t.get("target_type") or "page", queries=", ".join(f'"{q}"' for q in t["queries"][:3]) or "(none recorded)",
            anchor=anchor, words=SENTENCE_WORDS - 5,
            again=f"Your last attempt was refused because {problem}. Fix that.\n" if problem else "",
        )
        try:
            raw = extract_json(ask(prompt))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"The sentence could not be written ({type(exc).__name__}: {str(exc)[:120]})."}
        sentence = " ".join(str((raw.get("sentence") if isinstance(raw, dict) else "") or "").split())
        problem = sentence_problem(sentence, anchor, allowed)
        if problem is None:
            break
    if problem is not None:
        return {"ok": False, "reason": f"The sentence written could not be used: {problem}. Write it by hand, or try another link text."}
    row = db.query(InlinkState).filter(InlinkState.client_id == client.id, InlinkState.source_url == source, InlinkState.target_url == target).one_or_none()
    if row is None:
        row = InlinkState(client_id=client.id, source_url=source, target_url=target, status="todo", created_by=who)
        db.add(row)
    # As the sentence writes them: the model may have changed the case of the first letter.
    written = re.search(re.escape(anchor), sentence, re.I).group(0)
    row.anchor, row.sentence, row.sentence_anchor = anchor, sentence, written
    db.commit()
    return {"ok": True, "sentence": sentence, "anchor": written}


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
