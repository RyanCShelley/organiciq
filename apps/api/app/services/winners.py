"""Who is winning for a term, and what they do that the client's page does not.

Two places a term can be won: the search results page, and the answers the AI platforms give to its paired prompt.
For search the winners are the top-ranking pages; for the platforms they are the brands named and the pages cited,
which the LLM tracker already records for every prompt it asks.

To say what a winner does differently its page has to be read, not guessed at from a title. Up to three ranking
pages and three cited pages are fetched, under the crawler's own name, obeying each site's robots.txt, with no
second attempt under any other name. A page that refuses is listed as not read. What comes back is reduced to an
outline (headings, the paragraph under each, markup types, counts), and a model compares the client's outline with
the winners'. Every gap it returns must point at pages it was shown, and says whether it was observed in them or
inferred. Nothing here claims that copying a winner produces a ranking or a citation.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from typing import Any, Awaitable, Callable
from urllib import robotparser
from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from app.decisions import action_context as ac
from app.ingestion.crawler.fetch import USER_AGENT, challenge_reason
from app.ingestion.crawler.parse import parse_page
from app.ingestion.crawler.safe_http import PublicOnlyTransport
from app.models.client import Client
from app.models.llm_visibility import LlmResponse, LlmRun
from app.services import llm_evidence

logger = logging.getLogger("organiciq.winners")

#: How many winning pages are read for each of search and the AI platforms.
PAGES_READ = 3
TIMEOUT_SECONDS = 15.0
MAX_BODY_BYTES = 2_000_000
MAX_GAPS = 6


def _host(url: str) -> str:
    # A client's domain is stored bare ("shop.example"), which has no host until it is given a scheme.
    return (urlsplit(url if "//" in url else f"//{url}").hostname or "").lower().removeprefix("www.")


# ── the AI platforms ─────────────────────────────────────────────────────────


def llm_winners(db: Session, client: Client, search: str) -> dict[str, Any]:
    """What the platforms answered for the term's paired prompt in the latest run: brands in order, pages cited, and where the client stands."""
    keyword = llm_evidence.paired_keyword(db, client, search)
    if keyword is None:
        return {"ok": False, "reason": "No watchlist keyword with a paired AI prompt matches this search."}
    run = db.query(LlmRun).filter(LlmRun.client_id == client.id, LlmRun.status == "completed").order_by(LlmRun.started_at.desc()).first()
    if run is None:
        return {"ok": False, "reason": "No LLM visibility run has been done for this client yet."}
    prompt = " ".join(keyword.paired_ai_prompt.split())
    rows = [
        r for r in db.query(LlmResponse).filter(LlmResponse.run_id == run.id)
        if r.visibility_type != "Error" and " ".join(r.query_text.split()).lower() == prompt.lower()
    ]
    if not rows:
        return {"ok": False, "reason": "The latest run did not ask this keyword's paired prompt (it was added after that run)."}
    own = _host(client.domain)
    cited: Counter[str] = Counter()
    where: dict[str, set[str]] = {}
    platforms = []
    for r in sorted(rows, key=lambda r: r.platform):
        urls = [u for u in (r.cited_urls or []) if u]
        for u in dict.fromkeys(urls):
            cited[u] += 1
            where.setdefault(u, set()).add(r.platform)
        platforms.append({
            "platform": r.platform, "brands": list(r.all_brands_ordered or [])[:8], "brand_mentioned": bool(r.brand_mentioned),
            "brand_rank": r.brand_rank, "total_brands": r.total_brands, "client_cited": bool(r.url_cited), "sources": len(urls),
        })
    pages = [
        {"url": u, "domain": _host(u), "platforms": sorted(where[u]), "own": _host(u) == own, "page_type": ac.classify_page(u)["name"]}
        for u, _ in cited.most_common(12)
    ]
    return {
        "ok": True, "prompt": prompt, "keyword": keyword.keyword, "run_date": run.started_at.date().isoformat(), "platforms": platforms,
        "cited_pages": pages, "client_cited_on": [p["platform"] for p in platforms if p["client_cited"]],
        "client_named_on": [p["platform"] for p in platforms if p["brand_mentioned"]],
    }


# ── reading a winner's page ──────────────────────────────────────────────────


def outline(url: str, body: str, headers: dict[str, str]) -> dict[str, Any]:
    """A page reduced to what can be compared: its headings, the paragraph under each, markup types and counts."""
    parsed = parse_page(url=url, body=body, headers=headers)
    return {
        "title": parsed.title, "h1": parsed.h1, "word_count": parsed.word_count,
        "sections": [{"heading": s.heading, "text": " ".join(s.first_paragraph.split())[:220], "has_table": s.has_table, "has_list": s.has_list} for s in parsed.sections[:25]],
        "schema_types": sorted({b.schema_type for b in parsed.schema_blocks if b.schema_type}),
        "faq_questions": len(parsed.faq_questions), "conversion_elements": parsed.conversion_elements,
    }


async def _read_one(client: httpx.AsyncClient, url: str, robots: dict[str, robotparser.RobotFileParser | None]) -> dict[str, Any]:
    origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    if origin not in robots:
        rules: robotparser.RobotFileParser | None = None
        try:
            answer = await client.get(f"{origin}/robots.txt")
            if answer.status_code == 200:
                rules = robotparser.RobotFileParser()
                rules.parse(answer.text.splitlines())
        except httpx.HTTPError:
            rules = None
        robots[origin] = rules
    rules = robots[origin]
    if rules is not None and not rules.can_fetch(USER_AGENT, url):
        return {"url": url, "read": False, "reason": "Its robots.txt disallows our reader, so it was not fetched."}
    try:
        answer = await client.get(url)
    except httpx.HTTPError as exc:
        return {"url": url, "read": False, "reason": f"It could not be fetched ({type(exc).__name__})."}
    body = answer.content[:MAX_BODY_BYTES].decode(answer.encoding or "utf-8", errors="replace")
    blocked = challenge_reason(answer.status_code, answer.headers, body[:3000])
    if blocked or answer.status_code != 200:
        return {"url": url, "read": False, "reason": f"It answered our reader with {blocked or f'HTTP {answer.status_code}'}, and was not asked again under another name."}
    found = outline(str(answer.url), body, {k.lower(): v for k, v in answer.headers.items()})
    if not found["title"] and not found["sections"]:
        return {"url": url, "read": False, "reason": "It came back with no readable content (it may need JavaScript)."}
    return {"url": url, "read": True, **found}


async def _read_all(urls: list[str]) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(
        transport=PublicOnlyTransport(), follow_redirects=True, max_redirects=3, timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        robots: dict[str, robotparser.RobotFileParser | None] = {}
        out = []
        for url in urls:  # One at a time: these are other people's sites, and three pages do not need a burst.
            out.append(await _read_one(client, url, robots))
        return out


def read_pages(urls: list[str], reader: Callable[[list[str]], Awaitable[list[dict[str, Any]]]] = _read_all) -> list[dict[str, Any]]:
    return asyncio.run(reader(urls)) if urls else []


# ── the comparison ───────────────────────────────────────────────────────────

PROMPT = """You are comparing one page with the pages that are winning for a term, to say what the winners do that this page does not.
Use ONLY the outlines below. Do not assume anything about a page that is not in its outline, and do not claim a change will produce a ranking or a citation.

Term: {search}
What the searcher is trying to do: {goal}
Search intent (read from the results page): {intent}

THE CLIENT'S PAGE ({page_type}): {page}
{own}

WINNING IN SEARCH (top ranking pages that could be read):
{search_winners}

WINNING IN THE AI PLATFORMS (pages the platforms cited for the prompt "{prompt}"):
{llm_winners}
{llm_standing}

Say:
1. Whether the client's page is the right page to win this term, judged against these winners.
2. Up to {max_gaps} gaps: things most of the winners do, relevant to what the searcher wants, that the client's page does not.
   Consider both a person (does it help them do what they came to do?) and a machine reading it (can the page's main content, names, attributes, prices and relationships be found, extracted and understood, section by section?).
   Skip anything the client's page already does. Skip differences that do not serve this searcher. Keep each change specific to this type of page.

Return ONLY this JSON:
{{
  "best_page": {{"verdict": "yes|partly|no", "why": "one or two sentences naming the evidence"}},
  "gaps": [{{
    "issue": "what the client's page lacks or does worse, stated as an observation",
    "evidence": "what in the outlines shows it, naming the winner(s)",
    "seen_on": ["the winner URLs that show it, exactly as given"],
    "change": "the specific change to make on the client's page",
    "expected_outcome": "what it should improve for the searcher or for a machine reading the page; no numbers",
    "validation": "how to check afterwards that it worked",
    "serves": "search|llm|both",
    "basis": "observed|inferred"
  }}]
}}
"basis" is "observed" when the outlines show it directly, "inferred" when you are reasoning from them. If the outlines do not support any gap, return an empty list."""


def _show(page: dict[str, Any]) -> str:
    lines = [f"- {page['url']}", f"  title: {page.get('title') or ''} | main heading: {page.get('h1') or ''} | {page.get('word_count') or 0} words | markup: {', '.join(page.get('schema_types') or []) or 'none'} | FAQ questions: {page.get('faq_questions') or 0}"]
    for s in (page.get("sections") or [])[:18]:
        extra = " [table]" if s.get("has_table") else " [list]" if s.get("has_list") else ""
        lines.append(f"  · {s['heading']}{extra}: {s.get('text') or ''}"[:300])
    return "\n".join(lines)


def compare(
    *, search: str, intent: dict[str, Any], page_url: str, page_type: str, own: dict[str, Any], search_pages: list[dict[str, Any]],
    llm_pages: list[dict[str, Any]], llm: dict[str, Any], ask: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """`{ok, best_page, gaps}`. A gap is kept only if it names winners it was shown and gives its evidence."""
    read_search = [p for p in search_pages if p.get("read")]
    read_llm = [p for p in llm_pages if p.get("read")]
    if not read_search and not read_llm:
        return {"ok": False, "reason": "None of the winning pages could be read, so there is nothing to compare with.", "gaps": [], "best_page": None}
    if ask is None:
        from app.schema_tools import llm as model

        ask = lambda prompt: model.call("quick", prompt, max_tokens=3000)[0]  # noqa: E731
    standing = ""
    if llm.get("ok"):
        standing = "Where the client stands in those answers: " + "; ".join(
            f"{p['platform']}: {'cited' if p['client_cited'] else 'not cited'}, {'named' + (f' (rank {p['brand_rank']} of {p['total_brands']})' if p.get('brand_rank') else '') if p['brand_mentioned'] else 'not named'}"
            for p in llm["platforms"]
        )
    prompt = PROMPT.format(
        search=search, goal=intent.get("searcher_goal") or "not read", intent=intent.get("name") or "not read", page_type=page_type, page=page_url,
        own=_show({"url": page_url, **own}), search_winners="\n".join(_show(p) for p in read_search) or "(none could be read)",
        prompt=llm.get("prompt") or "none", llm_winners="\n".join(_show(p) for p in read_llm) or "(none could be read, or no prompt is paired)",
        llm_standing=standing, max_gaps=MAX_GAPS,
    )
    try:
        from app.schema_tools.llm import extract_json

        raw = extract_json(ask(prompt))
    except Exception as exc:
        return {"ok": False, "reason": f"The comparison could not be made ({type(exc).__name__}: {str(exc)[:120]}).", "gaps": [], "best_page": None}
    shown = {p["url"] for p in read_search + read_llm}
    gaps = []
    for g in (raw.get("gaps") or []) if isinstance(raw, dict) else []:
        if not isinstance(g, dict):
            continue
        seen = [u for u in (g.get("seen_on") or []) if u in shown]
        text = {k: " ".join(str(g.get(k) or "").split()) for k in ("issue", "evidence", "change", "expected_outcome", "validation")}
        # A gap that names no page it was shown, or gives no evidence or no change, is an opinion and is dropped.
        if not seen or not text["issue"] or not text["evidence"] or not text["change"]:
            continue
        serves = str(g.get("serves") or "").lower()
        gaps.append({
            **text, "seen_on": seen, "serves": serves if serves in ("search", "llm", "both") else "search",
            "basis": "observed" if str(g.get("basis") or "").lower() == "observed" else "inferred",
        })
    best = raw.get("best_page") if isinstance(raw, dict) else None
    verdict = str((best or {}).get("verdict") or "").lower()
    return {
        "ok": True, "gaps": gaps[:MAX_GAPS],
        "best_page": {"verdict": verdict, "why": " ".join(str(best.get("why") or "").split())} if isinstance(best, dict) and verdict in ("yes", "partly", "no") else None,
    }


def gather(
    db: Session, client: Client, *, search: str, intent: dict[str, Any], page_url: str, page_type: str, own: dict[str, Any],
    reader=_read_all, ask=None,
) -> dict[str, Any]:
    """Everything about who is winning for the term: the ranking pages, the platforms' answers, the pages read, and the gaps."""
    own_hosts = {_host(client.domain), _host(page_url)}
    ranked = [r for r in (intent.get("ranked") or []) if r.get("url")]
    llm = llm_winners(db, client, search)
    search_urls = [r["url"] for r in ranked if _host(r["url"]) not in own_hosts][:PAGES_READ]
    llm_urls = [p["url"] for p in (llm.get("cited_pages") or []) if not p["own"] and p["url"] not in search_urls][:PAGES_READ] if llm.get("ok") else []
    pages = read_pages(search_urls + llm_urls, reader)
    by_url = {p["url"]: p for p in pages}
    search_pages = [by_url[u] for u in search_urls if u in by_url]
    llm_pages = [by_url[u] for u in llm_urls if u in by_url]
    comparison = compare(search=search, intent=intent, page_url=page_url, page_type=page_type, own=own, search_pages=search_pages, llm_pages=llm_pages, llm=llm, ask=ask)
    trim = lambda p: {k: p.get(k) for k in ("url", "read", "reason", "title", "word_count", "schema_types")}  # noqa: E731
    return {
        "search": {"ranked": ranked, "client_ranks": [r for r in ranked if _host(r["url"]) in own_hosts], "pages": [trim(p) for p in search_pages]},
        "llm": {**llm, "pages": [trim(p) for p in llm_pages]},
        "comparison": comparison,
    }
