"""Diagnose a page against the search it ranks for.

The operator ticks a (search, page) pair on the Decision engine list. This reads that one
page live, builds the same facts the site crawl would, runs the tool's existing Visibility
rules on it, and reports three separate things:

- *prescriptions*: rules that fired, exactly as the catalog states them;
- *not judged*: rules that did not fire, with the reason, because "no action" and "this
  could not be checked" are different answers and the second must not read as the first;
- *observations*: plain facts about the page (is the search in the title, is it noindex,
  how its click-through compares with the benchmark). They are not recommendations: the
  catalog is explicit that an exact phrase missing from a page is not a content gap.

Only pages on the client's own domain are read, and only through the crawler's
public-addresses-only transport.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

import httpx

from app.decisions.catalog import VISIBILITY_ACTIONS, PageFacts, SectionFacts, _mentions
from app.decisions.ctr_curve import expected_ctr_percent
from app.decisions.slots import Prescription
from app.decisions.targets import Candidate, ScoredCandidate
from app.ingestion.crawler.parse import ParsedPage, parse_page
from app.ingestion.crawler.safe_http import PublicOnlyTransport
from app.services.page_eligibility import classify_page_url
from app.services.target_signals import _declares_faq, _entity_properties, _has_faq_section

MAX_BODY_BYTES = 3_000_000
TIMEOUT_SECONDS = 20.0
USER_AGENT = "OrganicIQ-page-diagnostic/1.0"

#: Why a rule that returned nothing returned nothing, in terms of what this reader cannot see.
_NOT_JUDGED = {
    "v6_rehoming": (
        "V-6",
        "Wrong page ranks",
        "Needs a declared owner page for the search to compare with. v2 has none until the Topic Hub "
        "mapping arrives, so it cannot say the wrong page is ranking.",
    ),
    "v7_mark_up_the_faq": ("V-7", "Mark up the FAQ", None),
    "v5_add_an_extractable_structure": (
        "V-5",
        "Add something an answer engine can lift",
        "Needs to know the search's SERP features (does an AI answer or snippet appear), which have not been "
        "pulled for this client.",
    ),
    "v4_internal_links": (
        "V-4",
        "Add internal links",
        "Needs the site-wide link crawl, to see which pages link here and compare with the site's median. "
        "That crawl has not completed for this client.",
    ),
}


class PageUnreadable(Exception):
    """The page could not be fetched: off the client's site, not public, an error, or too slow."""


@dataclass
class Fetched:
    status: int
    final_url: str
    headers: dict[str, str]
    body: str


def _host(value: str) -> str:
    host = (urlsplit(value if "//" in value else f"//{value}").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


async def _fetch(url: str) -> Fetched:
    async with httpx.AsyncClient(
        transport=PublicOnlyTransport(),
        follow_redirects=True,
        max_redirects=3,
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        response = await client.get(url)
        raw = response.content[:MAX_BODY_BYTES]
        return Fetched(
            status=response.status_code,
            final_url=str(response.url),
            headers={k.lower(): v for k, v in response.headers.items()},
            body=raw.decode(response.encoding or "utf-8", errors="replace"),
        )


def read_page(url: str, client_domain: str, fetch: Callable[[str], Awaitable[Fetched]] = _fetch) -> Fetched:
    """Fetch one page of the client's own site."""
    if urlsplit(url).scheme not in ("http", "https"):
        raise PageUnreadable("That is not a web address.")
    if _host(url) != _host(client_domain):
        raise PageUnreadable("That page is not on this client's website, so it is not read.")
    try:
        found = asyncio.run(fetch(url))
    except httpx.TooManyRedirects as exc:
        raise PageUnreadable("The page redirects too many times.") from exc
    except httpx.TimeoutException as exc:
        raise PageUnreadable("The page took too long to answer.") from exc
    except httpx.HTTPError as exc:
        raise PageUnreadable(f"The page could not be fetched: {exc}") from exc
    if _host(found.final_url) != _host(client_domain):
        raise PageUnreadable("The page redirects off this client's website, so it is not read.")
    return found


# ── facts ────────────────────────────────────────────────────────────────────


def facts_from(url: str, parsed: ParsedPage) -> PageFacts:
    """What the catalog reads about a page, from a page parsed live.

    Link counts are left at "unknown": a single page cannot say how many pages link to it,
    and the internal-links rule treats unknown as "cannot judge", never as "has none".
    """
    sections = parsed.sections or []
    faq_schema = any(_declares_faq(block.raw) for block in parsed.schema_blocks if block.raw is not None)
    entities: set[str] = set()
    for block in parsed.schema_blocks:
        if block.raw is not None:
            entities |= _entity_properties(block.raw)
    return PageFacts(
        url=url,
        title=parsed.title or None,
        description=parsed.description or None,
        headings=tuple(s.heading for s in sections),
        crawled=True,
        headings_known=True,
        faq_questions=tuple(parsed.faq_questions),
        entity_properties=frozenset(entities),
        has_faq_section=_has_faq_section([{"heading": s.heading} for s in sections]),
        has_faq_schema=faq_schema,
        sections=tuple(
            SectionFacts(heading=s.heading, has_table=s.has_table, has_list=s.has_list, has_stat=s.has_stat, level=s.level)
            for s in sections
        ),
        inbound_editorial_links=0,
        site_median_links=0.0,
        page_type=classify_page_url(url).page_type.value,
    )


def _scored(search: str, url: str, position: float, gain: float, page_type: str | None) -> ScoredCandidate:
    return ScoredCandidate(
        candidate=Candidate(
            keyword=search,
            target_url=url,
            ranking_url=url,
            position=position,
            volume=None,
            target_page_type=page_type,
            serp_features=frozenset(),
            serp_pulled=False,
        ),
        score=gain,
        factors={},
    )


def _prescription(p: Prescription) -> dict[str, Any]:
    out = asdict(p)
    out["branch"] = p.branch.value
    return out


# ── observations ─────────────────────────────────────────────────────────────


def observations(search: str, parsed: ParsedPage, fetched: Fetched, row: dict[str, Any]) -> list[dict[str, str]]:
    """Facts about the page. Problems first; none of them is a prescription."""
    found: list[dict[str, str]] = []

    def add(level: str, text: str) -> None:
        found.append({"level": level, "text": text})

    if fetched.status >= 400:
        add("problem", f"The page answers with an error ({fetched.status}).")
    if parsed.meta_noindex:
        add("problem", "The page is marked noindex, so Google is told not to show it.")
    if parsed.says_not_found:
        add("problem", "The page says it is not found while returning a normal response.")
    canonical = parsed.canonical_url
    if canonical and urlsplit(canonical).path.rstrip("/") != urlsplit(fetched.final_url).path.rstrip("/"):
        add("problem", f"The page's canonical points elsewhere ({canonical}), so Google may rank that address instead.")

    where = [
        name
        for name, present in (
            ("the title", _mentions(search, parsed.title)),
            ("the meta description", _mentions(search, parsed.description)),
            ("the main heading", _mentions(search, parsed.h1)),
            ("a subheading", any(_mentions(search, s.heading) for s in parsed.sections)),
        )
        if present
    ]
    if where:
        add("ok", f"“{search}” appears in {', '.join(where)}.")
    else:
        add("note", f"“{search}” does not appear as a phrase in the title, description, main heading or any subheading. "
                    "That alone is not a content gap: the page may answer it in other words.")

    impressions, clicks = row["impressions"], row["clicks"]
    if impressions >= 100:
        actual = clicks / impressions * 100
        expected = expected_ctr_percent(float(row["position"]))
        ratio = actual / expected if expected else 0
        verdict = "well under" if ratio < 0.5 else "under" if ratio < 0.9 else "in line with" if ratio <= 1.1 else "above"
        add("note", f"Click-through is {actual:.1f}% against {expected:.1f}% expected at position {row['position']:.1f}: {verdict} the benchmark.")
    else:
        add("note", f"Only {impressions} impressions, so click-through is not read against the benchmark.")

    add("note", f"{parsed.word_count:,} words, {len(parsed.sections)} headed sections, {len(parsed.faq_questions)} FAQ questions, "
                f"{parsed.conversion_elements} conversion elements.")
    return found


# ── the diagnostic ───────────────────────────────────────────────────────────


def diagnose(
    *,
    search: str,
    url: str,
    row: dict[str, Any],
    client_domain: str,
    fetch: Callable[[str], Awaitable[Fetched]] = _fetch,
) -> dict[str, Any]:
    """One (search, page) pair, read live. `row` carries the pair's numbers from the candidate list."""
    result: dict[str, Any] = {
        "search": search,
        "page": url,
        "position": row["position"],
        "impressions": row["impressions"],
        "clicks": row["clicks"],
        "read": {"ok": False, "status": None, "error": None, "at": datetime.now(timezone.utc).isoformat()},
        "observations": [],
        "prescriptions": [],
        "not_judged": [],
    }
    try:
        fetched = read_page(url, client_domain, fetch)
    except PageUnreadable as exc:
        result["read"]["error"] = str(exc)
        return result

    result["read"].update(ok=True, status=fetched.status, final_url=fetched.final_url)
    parsed = parse_page(url=fetched.final_url, body=fetched.body, headers=fetched.headers)
    facts = facts_from(url, parsed)
    scored = _scored(search, url, float(row["position"]), float(row.get("expected_extra_clicks") or 0), facts.page_type)

    if fetched.status >= 400:
        result["observations"] = observations(search, parsed, fetched, row)
        result["not_judged"] = [
            {"action_id": _NOT_JUDGED[a.__name__][0], "name": _NOT_JUDGED[a.__name__][1], "reason": "The page did not load, so no rule was run on it."}
            for a in VISIBILITY_ACTIONS
            if a.__name__ in _NOT_JUDGED
        ]
        return result

    for action in VISIBILITY_ACTIONS:
        info = _NOT_JUDGED.get(action.__name__)
        fired = action(scored, facts)
        if fired is not None:
            result["prescriptions"].append(_prescription(fired))
            continue
        action_id, name, reason = info or (action.__name__, action.__name__, "No reason recorded.")
        if action.__name__ == "v7_mark_up_the_faq":
            reason = (
                "The page already has FAQ markup." if facts.has_faq_schema
                else "The page has no FAQ section, so there are no questions to mark up."
            )
        result["not_judged"].append({"action_id": action_id, "name": name, "reason": reason})

    result["observations"] = observations(search, parsed, fetched, row)
    result["page_facts"] = {
        "title": facts.title,
        "description": facts.description,
        "h1": parsed.h1,
        "word_count": parsed.word_count,
        "schema_types": sorted({b.schema_type for b in parsed.schema_blocks if b.schema_type}),
    }
    return result
