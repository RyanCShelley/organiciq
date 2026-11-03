"""Site health: two scores from the site crawl, each kept per month.

SEO health says whether the site is technically sound for search. GEO readiness says whether it is ready to be read and
cited by AI answers, and is ported from the GEO Grader's retrievability score (same signals, same weights, same grades).
The weights are written down in the payload and shown on the screen.

The crawl is replaced each time it runs, so a month's scores are written when a crawl finishes and kept: the last crawl of a
month is that month's score, and it is locked once the month is over. A score on a crawl that stopped at its page limit
says so.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.crawl import (
    CRAWL_SOURCE_FIRST_PARTY,
    FactCrawlInternalLink,
    FactCrawlPageIssue,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from app.models.site_health import SiteHealthSnapshot
from app.services.competitors import bare_domain

DEFAULT_PAGE_LIMIT = 500
URLS_KEPT = 150  # per issue group, so a month's payload stays small and "new since last month" can still be told

#: SEO health: what is checked and how much each counts. Out of 100.
SEO_WEIGHTS = {"titles": 15, "descriptions": 10, "indexation": 15, "errors": 20, "redirects": 5, "links": 15, "schema": 10, "site_files": 10}
#: GEO readiness: the GEO Grader's weights.
GEO_WEIGHTS = {"schema": 15, "faq": 10, "entity": 10, "crawler": 10, "citation": 20, "depth": 15, "graph": 10, "attribution": 10}

GRADES = ((97, "A+"), (93, "A"), (90, "A-"), (87, "B+"), (83, "B"), (80, "B-"), (77, "C+"), (73, "C"), (70, "C-"), (67, "D+"), (63, "D"), (60, "D-"))


def grade(score: float) -> str:
    return next((g for floor, g in GRADES if score >= floor), "F")


def _month_of(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _last_day(month: str) -> date:
    y, m = int(month[:4]), int(month[5:7])
    nxt = date(y + (m == 12), (m % 12) + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


_PAGINATION = re.compile(r"(^|/)(page/\d+|page-\d+|p/\d+)/?$", re.I)
_PAGINATION_QUERY = re.compile(r"(^|&)(page|paged|pg|p)=\d+(&|$)", re.I)


def is_pagination(url: str) -> bool:
    """A numbered page of a list (/author/x/page/2, ?page=3): it repeats its list's template, so it is not judged on its own."""
    parts = urlsplit(url or "")
    return bool(_PAGINATION.search(parts.path) or _PAGINATION_QUERY.search(parts.query))


def _path(url: str) -> str:
    return urlsplit(url or "").path or "/"


# ── SEO health ────────────────────────────────────────────────────────────────


def _check(key: str, label: str, score: float, affected: int, total: int, urls: list[str], detail: str) -> dict[str, Any]:
    return {"key": key, "label": label, "weight": SEO_WEIGHTS[key], "score": round(max(0.0, min(100.0, score))), "affected": affected, "total": total, "detail": detail, "urls": urls[:URLS_KEPT]}


def seo_health(db: Session, client: Client, crawl_date: date) -> dict[str, Any]:
    snaps = (
        db.query(
            FactCrawlPageSnapshot.normalized_url, FactCrawlPageSnapshot.status_code, FactCrawlPageSnapshot.indexable, FactCrawlPageSnapshot.title,
            FactCrawlPageSnapshot.description, FactCrawlPageSnapshot.title_duplicate, FactCrawlPageSnapshot.description_duplicate,
            FactCrawlPageSnapshot.redirect_count, FactCrawlPageSnapshot.soft_404, FactCrawlPageSnapshot.blocked_by_robots,
        )
        .filter(FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY)
        .all()
    )
    total = len(snaps)
    # Numbered list pages (/page/2) repeat their list's template, so titles, descriptions, indexation and markup are not judged on them.
    # A broken or redirecting list page is still counted below: those are faults whatever the page is.
    ok_pages = [s for s in snaps if s.status_code is not None and 200 <= s.status_code < 300 and not s.blocked_by_robots and not is_pagination(s.normalized_url)]
    n_ok = len(ok_pages)
    checks: list[dict[str, Any]] = []

    def share(bad: int, whole: int) -> float:
        return bad / whole if whole else 0.0

    no_title = [s.normalized_url for s in ok_pages if not (s.title or "").strip()]
    dup_title = [s.normalized_url for s in ok_pages if (s.title or "").strip() and s.title_duplicate]
    bad = len(no_title) + len(dup_title)
    checks.append(_check("titles", "Page titles", 100 * (1 - share(bad, n_ok)), bad, n_ok, no_title + dup_title,
                         f"{len(no_title)} without a title, {len(dup_title)} sharing a title with another page"))
    no_desc = [s.normalized_url for s in ok_pages if not (s.description or "").strip()]
    dup_desc = [s.normalized_url for s in ok_pages if (s.description or "").strip() and s.description_duplicate]
    bad = len(no_desc) + len(dup_desc)
    checks.append(_check("descriptions", "Meta descriptions", 100 * (1 - share(bad, n_ok)), bad, n_ok, no_desc + dup_desc,
                         f"{len(no_desc)} without a description, {len(dup_desc)} sharing one with another page"))
    blocked = [s.normalized_url for s in ok_pages if not s.indexable]
    checks.append(_check("indexation", "Pages open to search engines", 100 * (1 - share(len(blocked), n_ok)), len(blocked), n_ok, blocked,
                         f"{len(blocked)} pages answer normally but ask not to be indexed"))
    errors = [s.normalized_url for s in snaps if (s.status_code or 0) >= 400 or s.soft_404]
    checks.append(_check("errors", "Broken pages (404, server errors, pages that say not found)", 100 * (1 - min(1.0, 5 * share(len(errors), total))), len(errors), total, errors,
                         f"{len(errors)} of {total} addresses are broken"))
    chains = [s.normalized_url for s in snaps if (s.redirect_count or 0) > 1]
    checks.append(_check("redirects", "Redirect chains", 100 * (1 - min(1.0, 10 * share(len(chains), total))), len(chains), total, chains,
                         f"{len(chains)} {'address passes' if len(chains) == 1 else 'addresses pass'} through more than one redirect"))

    status = {s.normalized_url: (s.status_code or 0) for s in snaps}
    edges = {(a, b) for a, b in db.query(FactCrawlInternalLink.from_url, FactCrawlInternalLink.to_url).filter(
        FactCrawlInternalLink.client_id == client.id, FactCrawlInternalLink.source == CRAWL_SOURCE_FIRST_PARTY)}
    broken_edges = [(a, b) for a, b in edges if status.get(b, 0) >= 400]
    broken_targets = sorted({b for _, b in broken_edges})
    checks.append(_check("links", "Internal links to broken pages", 100 * (1 - min(1.0, 10 * share(len(broken_edges), len(edges)))), len(broken_edges), len(edges), broken_targets,
                         f"{len(broken_edges)} of {len(edges)} internal links point at a broken page ({len(broken_targets)} different pages)"))

    with_schema = {u for (u,) in db.query(FactCrawlPageSchema.normalized_url).filter(FactCrawlPageSchema.client_id == client.id, FactCrawlPageSchema.parse_error.is_(None)).distinct()}
    indexable_ok = [s.normalized_url for s in ok_pages if s.indexable]
    missing = [u for u in indexable_ok if u not in with_schema]
    checks.append(_check("schema", "Pages with structured data", 100 * (1 - share(len(missing), len(indexable_ok))), len(missing), len(indexable_ok), missing,
                         f"{len(missing)} of {len(indexable_ok)} indexable pages carry no structured data"))

    site = [c for (c,) in db.query(FactCrawlPageIssue.issue_code).filter(FactCrawlPageIssue.client_id == client.id, FactCrawlPageIssue.source == CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageIssue.normalized_url.is_(None))]
    cost = {"no_robots": 40, "robots_not_accessible": 40, "robots_disallow_crawling": 100, "sitemap_missing": 30, "robots_has_errors": 30}
    lost = sum(cost.get(c, 0) for c in site)
    names = {"no_robots": "no robots.txt", "robots_not_accessible": "robots.txt could not be read", "robots_disallow_crawling": "robots.txt blocks crawling", "sitemap_missing": "no sitemap found", "robots_has_errors": "the declared sitemap does not load"}
    problems = [names[c] for c in site if c in names]
    checks.append(_check("site_files", "robots.txt and sitemap", 100 - lost, len(problems), 2, problems, "; ".join(problems) or "robots.txt and the sitemap are in place"))

    score = round(sum(c["weight"] * c["score"] for c in checks) / sum(SEO_WEIGHTS.values()))
    return {"score": score, "grade": grade(score), "checks": checks, "pages": total}


# ── GEO readiness (ported from the GEO Grader) ───────────────────────────────

_LD_TYPES = ("localbusiness", "organization", "service", "faqpage", "product", "professionalservice")
_ATTRIBUTION = ("source:", "according to", "based on", "references:", "[", "cited")
_MONTHS = re.compile(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", re.I)


def _schema_signal(rows: list[Any]) -> tuple[int, dict[str, Any]]:
    """JSON-LD anywhere 40, +10 for each business-relevant type in it (to 80), microdata +20."""
    ld = [r for r in rows if r.syntax == "json_ld"]
    score = 0
    found: list[str] = []
    if ld:
        score += 40
        text = " ".join(((r.schema_type or "") + " " + (r.raw_text or "")).lower() for r in ld)
        for t in _LD_TYPES:
            if t in text:
                score += 10
                found.append(t)
        score = min(score, 80)
    if any(r.syntax == "microdata" for r in rows):
        score += 20
    return min(score, 100), {"json_ld_blocks": len(ld), "types": found, "microdata": any(r.syntax == "microdata" for r in rows)}


FAQ_PAGES = 25


def _faq_pages(db: Session, client: Client, rows: list[Any], snaps: list[Any]) -> tuple[list[tuple[str, float | None]], set[str]]:
    """The pages FAQ markup is judged on, and which of them carry it.

    A page-by-page measure: the 25 pages Search Console shows most in the last 90 days (the ones that matter), or, with no Search
    Console data, the first 25 indexable pages crawled. Each either has FAQPage markup or does not.
    """
    from app.models.gsc import FactGscQueryPage

    ok = {s.normalized_url for s in snaps if s.status_code and 200 <= s.status_code < 300 and s.indexable and not is_pagination(s.normalized_url)}
    newest = db.query(func.max(FactGscQueryPage.date)).filter(FactGscQueryPage.client_id == client.id).scalar()
    pages: list[tuple[str, float | None]] = []
    if newest:
        top = db.query(FactGscQueryPage.normalized_url, func.sum(FactGscQueryPage.impressions)).filter(
            FactGscQueryPage.client_id == client.id, FactGscQueryPage.date > date.fromordinal(newest.toordinal() - 90)).group_by(FactGscQueryPage.normalized_url).order_by(func.sum(FactGscQueryPage.impressions).desc()).limit(FAQ_PAGES * 3).all()
        pages = [(u, float(i)) for u, i in top if u in ok][:FAQ_PAGES]
    if not pages:
        pages = [(u, None) for u in sorted(ok)[:FAQ_PAGES]]
    faq = {r.normalized_url for r in rows if r.syntax == "json_ld" and "faqpage" in ((r.schema_type or "") + (r.raw_text or "")).lower()}
    return pages, faq


def _faq_signal(pages: list[tuple[str, float | None]], faq: set[str]) -> int:
    """The share of those pages that carry FAQPage markup. (The GEO Grader scores one page, and gives 50 for the markup and 50 for
    headings and accordions, which the crawl does not store; here each page either has the markup or does not.)"""
    return round(100 * sum(1 for u, _ in pages if u in faq) / len(pages)) if pages else 0


def _entity_signal(db: Session, client: Client, rows: list[Any], snaps: list[Any]) -> tuple[int, dict[str, Any]]:
    """Title and description on the indexable pages (25 each, by share), an about page 15, a contact page 10, a phone 15 and an
    address 10 (both read from the structured data)."""
    ok = [s for s in snaps if s.status_code and 200 <= s.status_code < 300 and s.indexable and not is_pagination(s.normalized_url)]
    t = (sum(1 for s in ok if (s.title or "").strip()) / len(ok)) if ok else 0
    d = (sum(1 for s in ok if (s.description or "").strip()) / len(ok)) if ok else 0
    paths = [_path(s.normalized_url).lower() for s in snaps if s.status_code and 200 <= s.status_code < 300]
    about = any("/about" in p for p in paths)
    contact = any("/contact" in p for p in paths)
    blob = " ".join((r.raw_text or "").lower() for r in rows)
    phone = "telephone" in blob
    address = "streetaddress" in blob or "postaladdress" in blob or '"address"' in blob
    score = round(25 * t + 25 * d + 15 * about + 10 * contact + 15 * phone + 10 * address)
    return min(score, 100), {"title_share": round(t, 2), "description_share": round(d, 2), "about_page": about, "contact_page": contact, "phone_in_markup": phone, "address_in_markup": address}


def _crawler_signal(db: Session, client: Client) -> tuple[int, list[str]]:
    row = db.query(FactCrawlPageIssue.raw).filter(FactCrawlPageIssue.client_id == client.id, FactCrawlPageIssue.issue_code == "ai_crawlers_blocked").first()
    agents = [str(a).lower() for a in (row[0] or {}).get("agents", [])] if row else []
    groups = {"gptbot": ("gptbot", "oai-searchbot"), "ccbot": ("ccbot",), "google-extended": ("google-extended",), "chatgpt-user": ("chatgpt-user",), "anthropic": ("claudebot", "claude-web", "anthropic")}
    blocked = [g for g, names in groups.items() if any(a in agents for a in names)]
    return max(0, 100 - 20 * len(blocked)), blocked


def _depth(text: str, brand: str) -> int:
    score = 0
    if re.search(r"\b\d+%|\$[\d,]+|\b\d{4}\b", text):
        score += 20
    if _MONTHS.search(text):
        score += 15
    if re.search(r"\b(CEO|founder|president|director|manager)\b", text, re.I):
        score += 15
    if len(text) > 300:
        score += 15
    if len(text) > 600:
        score += 10
    if brand and brand.lower() in text.lower():
        score += 15
    if re.search(r"\(\d{3}\)", text):
        score += 10
    return min(score, 100)


def _answer_signals(db: Session, client: Client) -> dict[str, Any] | None:
    """From the latest finished AI run: how often the answers carry the site's address, how much detail they give, whether they
    attribute sources, and how many platforms name the brand."""
    from app.models.llm_visibility import ClientLlmSettings, LlmResponse, LlmRun

    run = db.query(LlmRun).filter(LlmRun.client_id == client.id, LlmRun.status == "completed").order_by(LlmRun.started_at.desc()).first()
    if run is None:
        return None
    rows = [r for r in db.query(LlmResponse).filter(LlmResponse.run_id == run.id, LlmResponse.client_id == client.id).all() if r.visibility_type != "Error" and (r.full_response or "").strip()]
    if not rows:
        return None
    saved = db.query(ClientLlmSettings.brand_name).filter(ClientLlmSettings.client_id == client.id).scalar()
    brand = (saved or client.client_name or "").strip()
    domain = bare_domain(client.domain).lower()
    cited = sum(1 for r in rows if bool(r.url_cited) or (domain and domain in (r.full_response or "").lower()))
    attributed = sum(1 for r in rows if any(m in (r.full_response or "").lower() for m in _ATTRIBUTION))
    depth = [_depth(r.full_response or "", brand) for r in rows]
    platforms = {r.platform for r in rows if r.brand_mentioned}
    by_prompt: dict[str, dict[str, Any]] = {}
    for r, d in zip(rows, depth):
        p = by_prompt.setdefault(" ".join((r.query_text or "").split()), {"answers": 0, "cited": 0, "attributed": 0, "depth": 0, "platforms": set()})
        p["answers"] += 1
        p["cited"] += bool(r.url_cited) or bool(domain and domain in (r.full_response or "").lower())
        p["attributed"] += any(m in (r.full_response or "").lower() for m in _ATTRIBUTION)
        p["depth"] += d
        p["platforms"].add(r.platform)
    return {
        "by_prompt": by_prompt, "platforms_all": sorted({r.platform for r in rows}),
        "run_date": run.started_at.date().isoformat(), "answers": len(rows),
        "citation": min(100, round(cited / len(rows) * 100)), "depth": min(100, round(sum(depth) / len(depth))),
        "attribution": min(100, round(attributed / len(rows) * 100)), "graph": min(len(platforms) * 25, 100), "platforms_naming": sorted(platforms),
    }


def _item(text: str, url: str | None = None) -> dict[str, str | None]:
    return {"text": text, "url": url}


def _prompt_pages(db: Session, client: Client) -> dict[str, tuple[str, str | None]]:
    """Each watchlist prompt, with its keyword and the page that shows most for that keyword in Search Console (the page to improve)."""
    from app.models.gsc import FactGscQueryPage
    from app.models.watchlist import WatchlistKeyword
    from app.services.review_visibility import key_of

    pairs = {" ".join(p.split()): k for k, p in db.query(WatchlistKeyword.keyword, WatchlistKeyword.paired_ai_prompt).filter(WatchlistKeyword.client_id == client.id, WatchlistKeyword.paired_ai_prompt.isnot(None)) if p}
    if not pairs:
        return {}
    keys = {key_of(k) for k in pairs.values()}
    q = func.lower(func.trim(FactGscQueryPage.query))
    newest = db.query(func.max(FactGscQueryPage.date)).filter(FactGscQueryPage.client_id == client.id).scalar()
    best: dict[str, tuple[str, float]] = {}
    if newest:
        for key, url, imp in db.query(q, FactGscQueryPage.normalized_url, func.sum(FactGscQueryPage.impressions)).filter(
            FactGscQueryPage.client_id == client.id, FactGscQueryPage.date > date.fromordinal(newest.toordinal() - 90), q.in_(keys)).group_by(q, FactGscQueryPage.normalized_url):
            if float(imp or 0) > best.get(key, ("", 0.0))[1]:
                best[key] = (url, float(imp or 0))
    return {prompt: (kw, best.get(key_of(kw), (None, 0))[0]) for prompt, kw in pairs.items()}


def _geo_items(db: Session, client: Client, rows: list[Any], snaps: list[Any], answers: dict[str, Any] | None, blocked: list[str], entity_detail: dict[str, Any]) -> dict[str, list[dict[str, str | None]]]:
    """What to fix, per signal: pages for the page-level signals, prompts (with the page to improve) for the answer-based ones."""
    from app.models.gsc import FactGscQueryPage

    home = f"https://{bare_domain(client.domain)}/"
    ok = [s for s in snaps if s.status_code and 200 <= s.status_code < 300 and s.indexable and not is_pagination(s.normalized_url)]
    items: dict[str, list[dict[str, str | None]]] = {}

    with_ld = {r.normalized_url for r in rows if r.syntax == "json_ld" and not r.parse_error}
    items["schema"] = [_item("No structured data on this page", s.normalized_url) for s in ok if s.normalized_url not in with_ld]
    text = " ".join(((r.schema_type or "") + " " + (r.raw_text or "")).lower() for r in rows if r.syntax == "json_ld")
    if "organization" not in text and "localbusiness" not in text:
        items["schema"].insert(0, _item("No Organization markup anywhere: add it to the homepage so the brand reads as one entity", home))

    pages, faq_urls = _faq_pages(db, client, rows, snaps)
    items["faq"] = [
        _item(f"Shows {round(imp):,} times in Google in 90 days and has no FAQ markup" if imp is not None else "No FAQ markup on this page", u)
        for u, imp in pages if u not in faq_urls
    ]

    ent = [_item("No title", s.normalized_url) for s in ok if not (s.title or "").strip()] + [_item("No meta description", s.normalized_url) for s in ok if not (s.description or "").strip()]
    if not entity_detail.get("about_page"):
        ent.insert(0, _item("No about page was found in the crawl"))
    if not entity_detail.get("contact_page"):
        ent.insert(0, _item("No contact page was found in the crawl"))
    if not entity_detail.get("phone_in_markup"):
        ent.insert(0, _item("No phone number in the structured data: add it to the Organization markup", home))
    if not entity_detail.get("address_in_markup"):
        ent.insert(0, _item("No address in the structured data: add it to the Organization markup", home))
    items["entity"] = ent

    robots = f"https://{bare_domain(client.domain)}/robots.txt"
    names = {"gptbot": "GPTBot", "ccbot": "CCBot", "google-extended": "Google-Extended", "chatgpt-user": "ChatGPT-User", "anthropic": "Anthropic's crawler"}
    items["crawler"] = [_item(f"{names.get(b, b)} is blocked in robots.txt, so that AI cannot read the site", robots) for b in blocked]

    for key in ("citation", "depth", "graph", "attribution"):
        items[key] = []
    if answers:
        pages = _prompt_pages(db, client)
        for prompt, p in sorted(answers["by_prompt"].items(), key=lambda kv: kv[1]["cited"] / max(1, kv[1]["answers"])):
            kw, page = pages.get(prompt, (None, None))
            n = p["answers"]
            if p["cited"] == 0:
                items["citation"].append(_item(f"“{prompt}”: none of {n} answers carry the site's address" + (f". Page to strengthen for “{kw}”." if page else (f". No page shows for “{kw}” yet." if kw else "")), page))
        for prompt, p in sorted(answers["by_prompt"].items(), key=lambda kv: kv[1]["depth"] / max(1, kv[1]["answers"]))[:25]:
            kw, page = pages.get(prompt, (None, None))
            avg = round(p["depth"] / max(1, p["answers"]))
            if avg < 50:
                items["depth"].append(_item(f"“{prompt}”: answers give little specific detail ({avg} of 100)", page))
        for prompt, p in answers["by_prompt"].items():
            if p["attributed"] == 0:
                kw, page = pages.get(prompt, (None, None))
                items["attribution"].append(_item(f"“{prompt}”: no answer attributes a source", page))
        for platform in answers["platforms_all"]:
            if platform not in answers["platforms_naming"]:
                items["graph"].append(_item(f"{platform} does not name the brand in any answer: it may not know the brand as an entity yet"))
    return items


def geo_readiness(db: Session, client: Client) -> dict[str, Any]:
    rows = db.query(FactCrawlPageSchema).filter(FactCrawlPageSchema.client_id == client.id).all()
    snaps = db.query(FactCrawlPageSnapshot).filter(FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY).all()
    schema, schema_detail = _schema_signal(rows)
    entity, entity_detail = _entity_signal(db, client, rows, snaps)
    crawler, blocked = _crawler_signal(db, client)
    answers = _answer_signals(db, client)
    faq_pages = _faq_pages(db, client, rows, snaps)
    signals = [
        {"key": "schema", "label": "Structured data", "weight": GEO_WEIGHTS["schema"], "score": schema, "measured": True, "detail": schema_detail, "note": "Read from every crawled page, not only the homepage."},
        {"key": "faq", "label": "FAQ markup", "weight": GEO_WEIGHTS["faq"], "score": _faq_signal(*faq_pages), "measured": True, "detail": {"pages": len(faq_pages[0]), "with_markup": sum(1 for u, _ in faq_pages[0] if u in faq_pages[1])}, "note": "Page by page: the share of the 25 pages Google shows most that carry FAQPage markup."},
        {"key": "entity", "label": "Entity clarity", "weight": GEO_WEIGHTS["entity"], "score": entity, "measured": True, "detail": entity_detail, "note": "Titles and descriptions by share of pages; phone and address from the markup."},
        {"key": "crawler", "label": "AI-crawler access", "weight": GEO_WEIGHTS["crawler"], "score": crawler, "measured": True, "detail": {"blocked": blocked}, "note": "20 points off for each of GPTBot, CCBot, Google-Extended, ChatGPT-User and Anthropic blocked in robots.txt."},
    ]
    for key, label, note in (
        ("citation", "Citation", "Answers that carry the site's address."),
        ("depth", "Content depth", "How much specific detail the answers give."),
        ("graph", "Knowledge graph presence", "25 points for each platform that names the brand (4 platforms is full marks)."),
        ("attribution", "Source attribution", "Answers that attribute their sources."),
    ):
        signals.append({"key": key, "label": label, "weight": GEO_WEIGHTS[key], "score": answers[key] if answers else None, "measured": answers is not None, "detail": {}, "note": note})
    items = _geo_items(db, client, rows, snaps, answers, blocked, entity_detail)
    for sig in signals:
        found = items.get(sig["key"], []) if sig["measured"] else []
        sig["items"] = found[:URLS_KEPT]
        sig["affected"] = len(found)
    measured = [s for s in signals if s["measured"]]
    weight = sum(s["weight"] for s in measured)
    score = round(sum(s["weight"] * s["score"] for s in measured) / weight) if weight else 0
    public = {k: v for k, v in (answers or {}).items() if k != "by_prompt"} or None
    return {"score": score, "grade": grade(score), "signals": signals, "answers": public, "partial": len(measured) < len(signals)}


# ── The month ─────────────────────────────────────────────────────────────────


def _crawl_info(db: Session, client: Client) -> dict[str, Any] | None:
    row = db.query(func.max(FactCrawlPageSnapshot.snapshot_date), func.count()).filter(
        FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY).one()
    if not row[0]:
        return None
    limit = client.crawl_page_limit or DEFAULT_PAGE_LIMIT
    return {"date": row[0], "pages": row[1], "limit": limit, "hit_limit": row[1] >= limit}


def build(db: Session, client: Client) -> dict[str, Any] | None:
    """Both scores from the crawl held now, or None if the site has not been crawled."""
    info = _crawl_info(db, client)
    if info is None:
        return None
    return {
        "crawl": {"date": info["date"].isoformat(), "pages": info["pages"], "limit": info["limit"], "hit_limit": info["hit_limit"]},
        "seo": seo_health(db, client, info["date"]),
        "geo": geo_readiness(db, client),
        "weights": {"seo": SEO_WEIGHTS, "geo": GEO_WEIGHTS},
    }


def record(db: Session, client: Client, today: date | None = None) -> SiteHealthSnapshot | None:
    """Write the scores for the month of the crawl just held. Each crawl in a month overwrites that month's row, so the last
    crawl of the month is its score; a month that is over is no longer written."""
    payload = build(db, client)
    if payload is None:
        return None
    crawl_date = date.fromisoformat(payload["crawl"]["date"])
    month = _month_of(crawl_date)
    row = db.query(SiteHealthSnapshot).filter(SiteHealthSnapshot.client_id == client.id, SiteHealthSnapshot.month == month).one_or_none()
    if row is None:
        row = SiteHealthSnapshot(client_id=client.id, month=month)
        db.add(row)
    from fastapi.encoders import jsonable_encoder

    row.crawl_date, row.payload = crawl_date, jsonable_encoder(payload)
    db.commit()
    return row


def _issue_sets(payload: dict[str, Any] | None) -> dict[str, set[str]]:
    sets = {c["key"]: set(c["urls"]) for c in (payload or {}).get("seo", {}).get("checks", [])}
    for sig in (payload or {}).get("geo", {}).get("signals", []):
        sets[f"geo:{sig['key']}"] = {f"{i.get('url') or ''}|{i['text']}" for i in sig.get("items") or []}
    return sets


def months(db: Session, client: Client) -> list[str]:
    """Months that have scores, newest first."""
    return [m for (m,) in db.query(SiteHealthSnapshot.month).filter(SiteHealthSnapshot.client_id == client.id).order_by(SiteHealthSnapshot.month.desc())]


def default_month(db: Session, client: Client) -> str | None:
    """The month of the crawl held now (or the newest scored month if the site has no crawl)."""
    info = _crawl_info(db, client)
    return _month_of(info["date"]) if info else next(iter(months(db, client)), None)


def for_month(db: Session, client: Client, month: str, today: date | None = None) -> dict[str, Any] | None:
    """The month's scores with the month before beside them, and what is new or fixed since."""
    today = today or date.today()
    over = _last_day(month) < today
    row = db.query(SiteHealthSnapshot).filter(SiteHealthSnapshot.client_id == client.id, SiteHealthSnapshot.month == month).one_or_none()
    info = _crawl_info(db, client)
    # The crawl held now belongs to one month. While that month is running its row follows each look; once it is over the row is kept as it was.
    if info is not None and _month_of(info["date"]) == month and (row is None or not over):
        record(db, client)
    row = db.query(SiteHealthSnapshot).filter(SiteHealthSnapshot.client_id == client.id, SiteHealthSnapshot.month == month).one_or_none()
    if row is None:
        return None
    y, m = int(month[:4]), int(month[5:7])
    prev_month = f"{y - (m == 1):04d}-{(m - 2) % 12 + 1:02d}"
    prev = db.query(SiteHealthSnapshot).filter(SiteHealthSnapshot.client_id == client.id, SiteHealthSnapshot.month == prev_month).one_or_none()
    payload = row.payload
    changes = []
    if prev is not None:
        now_sets, was_sets = _issue_sets(payload), _issue_sets(prev.payload)
        labels = {c["key"]: c["label"] for c in payload["seo"]["checks"]}
        labels.update({f"geo:{x['key']}": f"GEO: {x['label']}" for x in payload["geo"]["signals"]})
        for key, urls in now_sets.items():
            new, fixed = sorted(urls - was_sets.get(key, set())), sorted(was_sets.get(key, set()) - urls)
            if new or fixed:
                changes.append({"key": key, "label": labels[key], "new": new[:50], "fixed": fixed[:50], "new_count": len(new), "fixed_count": len(fixed)})
    locked = over
    return {
        **payload, "month": month, "locked": locked, "crawl_date": row.crawl_date.isoformat(),
        "previous": {"month": prev_month, "seo": prev.payload["seo"]["score"], "geo": prev.payload["geo"]["score"], "crawl_date": prev.crawl_date.isoformat()} if prev is not None else None,
        "changes": changes,
    }
