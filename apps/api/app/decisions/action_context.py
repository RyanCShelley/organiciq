"""What a growth action must know before it is offered: the search's intent, the page's type, whether
the two fit, how far a change would reach, and how good the evidence is.

A growth action used to be chosen by impressions and built from the same three parts whatever the page
was: answer the question at the top, use the searched phrasing, add an FAQ. A product page that showed
for "what is the difference between tanning oil and sunscreen" was told to open with an essay. And a
page the reader could not fetch produced an error and nothing else, where the refusal was itself worth
looking into.

Everything here is a rule, not a model's opinion: the same inputs give the same answer, and each answer
carries the signals it was read from, so a person can see why and overrule it. Nothing is invented when
a signal is missing: the answer is "unknown" or "unverified".
"""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlsplit

from app.decisions import serp_intent
from app.schema_tools.page_type import detect_page_type

# ── search intent ────────────────────────────────────────────────────────────
#
# Intent is read from the search's results page by `serp_intent`: what type and style of content ranks and which
# features show. Nothing here guesses it from the words of the search, a tool's label, or this site's own pages.
# With no results page the intent is "not read", and everything that depends on intent is held back.

INFORMATIONAL, COMMERCIAL, TRANSACTIONAL, NAVIGATIONAL, LOCAL, MIXED = (
    serp_intent.INFORMATIONAL, serp_intent.COMMERCIAL, serp_intent.TRANSACTIONAL, serp_intent.NAVIGATIONAL, serp_intent.LOCAL, serp_intent.MIXED,
)
NOT_READ, INSUFFICIENT = serp_intent.NOT_READ, serp_intent.INSUFFICIENT
INTENT_NAMES = serp_intent.INTENT_NAMES


def is_read(intent: dict[str, Any]) -> bool:
    return bool(intent.get("read"))


# ── page type ────────────────────────────────────────────────────────────────

PRODUCT, CATEGORY, SERVICE, LOCATION, ARTICLE, RESOURCE, HOMEPAGE, ABOUT, LANDING, OTHER = (
    "product", "category", "service", "location", "article", "resource", "homepage", "about", "landing", "unknown",
)
PAGE_NAMES = {
    PRODUCT: "Product page", CATEGORY: "Category or collection page", SERVICE: "Service page", LOCATION: "Location page",
    ARTICLE: "Blog or article", RESOURCE: "Resource or guide", HOMEPAGE: "Homepage", ABOUT: "About or company page",
    LANDING: "Landing page", OTHER: "Not established",
}
_FROM_DETECTED = {
    "editorial": ARTICLE, "product": PRODUCT, "service": SERVICE, "productized_service": SERVICE, "category": CATEGORY,
    "landing": LANDING, "faq": RESOURCE, "documentation": RESOURCE, "homepage": HOMEPAGE, "about": ABOUT, "generic": OTHER,
}
_LOCATION_PATH = re.compile(r"/(locations?|service-areas?|areas-we-serve|areas-served|cities|city|stores?/[^/]+)(/|$)", re.I)
_COLLECTION_PATH = re.compile(r"/collections?/[^/]+/?$", re.I)
#: What each type of page is for. A page's purpose is what a change to it must not break.
PAGE_PURPOSE = {
    PRODUCT: "sell the product", CATEGORY: "help a buyer find and choose a product", SERVICE: "win an enquiry for the service",
    LOCATION: "win a local enquiry", ARTICLE: "answer a question", RESOURCE: "explain or teach", HOMEPAGE: "say who the business is and route visitors",
    ABOUT: "say who the business is", LANDING: "convert a visitor on one offer", OTHER: "not established",
}
COMMERCIAL_PAGES = frozenset({PRODUCT, CATEGORY, SERVICE, LOCATION, LANDING})
INFORMATIONAL_PAGES = frozenset({ARTICLE, RESOURCE})


def classify_page(url: str, *, schema_types: Iterable[str] | None = None, title: str | None = None, h1: str | None = None) -> dict[str, Any]:
    """`{type, name, confidence, basis, purpose}`. The address alone is a guess; markup on the page is evidence."""
    schema = [s for s in (schema_types or []) if s]
    path = urlsplit(url).path or "/"
    by_all = detect_page_type(url, schema, title or h1)
    by_url = detect_page_type(url, [], None)
    kind = _FROM_DETECTED.get(by_all, OTHER)
    basis: list[str] = []
    if schema and by_all != by_url:
        basis.append(f"its markup ({', '.join(sorted(set(schema))[:4])})")
    elif schema and kind != OTHER:
        basis.append(f"its address and markup ({', '.join(sorted(set(schema))[:4])})")
    elif kind != OTHER and by_url == by_all:
        basis.append("its address")
    elif kind != OTHER:
        basis.append("its title")
    if kind in (PRODUCT, OTHER) and _COLLECTION_PATH.search(path) and "/products/" not in path:
        kind, basis = CATEGORY, ["its address (a collection)"]
    if kind in (SERVICE, OTHER, LANDING) and _LOCATION_PATH.search(path):
        kind, basis = LOCATION, ["its address (a location)"]
    if kind == OTHER:
        confidence = "none"
    elif any("markup" in b for b in basis):
        confidence = "high"
    else:
        confidence = "medium"
    return {
        "type": kind, "name": PAGE_NAMES[kind], "confidence": confidence, "basis": basis,
        "purpose": PAGE_PURPOSE[kind],
        "note": None if kind != OTHER else "Neither the address nor the page's markup says what kind of page this is.",
    }


# ── does the page suit the search ────────────────────────────────────────────

HIGH, MEDIUM, LOW, UNVERIFIED = "high", "medium", "low", "unverified"
_FIT: dict[str, dict[str, str]] = {
    INFORMATIONAL: {ARTICLE: HIGH, RESOURCE: HIGH, PRODUCT: LOW, CATEGORY: LOW, SERVICE: LOW, LOCATION: LOW, LANDING: LOW, HOMEPAGE: LOW, ABOUT: LOW},
    COMMERCIAL: {CATEGORY: HIGH, SERVICE: HIGH, LANDING: HIGH, PRODUCT: MEDIUM, ARTICLE: MEDIUM, RESOURCE: MEDIUM, LOCATION: MEDIUM, HOMEPAGE: MEDIUM, ABOUT: LOW},
    TRANSACTIONAL: {PRODUCT: HIGH, CATEGORY: HIGH, SERVICE: HIGH, LANDING: HIGH, LOCATION: HIGH, HOMEPAGE: MEDIUM, ARTICLE: LOW, RESOURCE: LOW, ABOUT: LOW},
    LOCAL: {LOCATION: HIGH, SERVICE: HIGH, HOMEPAGE: HIGH, LANDING: MEDIUM, PRODUCT: MEDIUM, CATEGORY: MEDIUM, ABOUT: MEDIUM, ARTICLE: LOW, RESOURCE: LOW},
    NAVIGATIONAL: {HOMEPAGE: HIGH, ABOUT: HIGH},
}


#: Ranking content types (as `serp_intent` names them) grouped by what the page is for.
SELLING, EXPLAINING, HOME = "selling", "explaining", "home"
_FAMILY = {
    "product page": SELLING, "category or collection page": SELLING, "service page": SELLING, "local listing": SELLING,
    "article or blog post": EXPLAINING, "guide or resource": EXPLAINING,
    "homepage": HOME,
}
_PAGE_FAMILY = {
    PRODUCT: SELLING, CATEGORY: SELLING, SERVICE: SELLING, LOCATION: SELLING, LANDING: SELLING,
    ARTICLE: EXPLAINING, RESOURCE: EXPLAINING, HOMEPAGE: HOME, ABOUT: HOME,
}
FAMILY_NAMES = {SELLING: "product, collection or service pages", EXPLAINING: "articles or guides", HOME: "homepages"}
#: Fewer ranking results than this with a known type, and what ranks is not enough to judge a page by.
MIN_RANKED = 5


def ranking_families(intent: dict[str, Any]) -> dict[str, int]:
    """How many of the ranking results are pages that sell, pages that explain, and homepages."""
    out: dict[str, int] = {}
    for kind, n in (intent.get("content_types") or {}).items():
        family = _FAMILY.get(kind)
        if family:
            out[family] = out.get(family, 0) + int(n)
    return out


def compatibility(intent: dict[str, Any], page: dict[str, Any]) -> dict[str, Any]:
    """Whether this page is a suitable destination for this search. Impressions do not enter into it.

    Judged first against what actually ranks: how many of the ranking results are the same kind of page as this
    one. None means the page does not suit the search, whatever the intent is called: "natural sunscreen" read as
    commercial, the old table said commercial suits a collection page, and all eight ranking results were articles.
    The intent table is the fallback for a results page whose content types could not be read.

    `leads` is the kind of page that ranks most, which is where the work is routed when this page does not suit.
    """
    if not is_read(intent):
        return {"level": UNVERIFIED, "why": f"Not judged: {intent['name'].lower()}.", "basis": "none", "leads": None}
    k = page["type"]
    if k == OTHER:
        return {"level": UNVERIFIED, "why": "Not judged: the page's type is not established.", "basis": "none", "leads": None}
    families = ranking_families(intent)
    total = sum((intent.get("content_types") or {}).values())
    # When the results page is split evenly between kinds of page, what the searcher is there to do says which kind leads:
    # someone buying is served by the pages that sell, someone learning by the pages that explain.
    prefers = {TRANSACTIONAL: SELLING, LOCAL: SELLING, INFORMATIONAL: EXPLAINING, NAVIGATIONAL: HOME}.get(intent.get("primary") or "")
    top = max(families.values()) if families else 0
    leading = [f for f, n in families.items() if n == top]
    leads = None if not leading else prefers if prefers in leading else leading[0]
    mine = _PAGE_FAMILY.get(k)
    if total >= MIN_RANKED and mine:
        matched = families.get(mine, 0)
        tied = len(leading) > 1 and mine in leading
        level = LOW if matched == 0 else HIGH if mine == leads or (tied and prefers not in leading) else MEDIUM
        shown = ", ".join(f"{n} {t}" for t, n in (intent.get("content_types") or {}).items())
        words = {HIGH: "suits", MEDIUM: "partly suits", LOW: "does not suit"}[level]
        return {
            "level": level, "basis": "what ranks", "leads": leads, "matched": matched, "total": total,
            "why": f"{matched} of the {total} ranking results are {FAMILY_NAMES[mine]}"
                   + (f", level with {FAMILY_NAMES[leads]}, and the search is {intent['name'].lower()}" if tied and prefers in leading and mine != leads else "")
                   + (f", level with other kinds, and the search is {intent['name'].lower()}" if tied and mine == leads else "")
                   + f", so a {page['name'].lower()} {words} this search. What ranks: {shown}.",
        }
    order = [HIGH, MEDIUM, LOW]
    levels = {i: _FIT.get(i, {}).get(k, MEDIUM) for i in (intent["primary"], intent.get("secondary")) if i}
    note = " Too few ranking results had a readable type to judge by what ranks, so this is from the intent alone."
    if intent["intent"] == MIXED:
        level = min(levels.values(), key=order.index)
        parts = ", ".join(f"{levels[i]} for the {INTENT_NAMES[i].lower()} side" for i in levels)
        return {"level": MEDIUM if level == HIGH else level, "basis": "intent", "leads": leads, "why": f"The search is mixed. A {page['name'].lower()} is there to {page['purpose']}: {parts}.{note}"}
    level = levels[intent["primary"]]
    words = {HIGH: "suits", MEDIUM: "partly suits", LOW: "does not suit"}[level]
    return {"level": level, "basis": "intent", "leads": leads, "why": f"A {page['name'].lower()} is there to {page['purpose']}, which {words} a search that is {intent['name'].lower()}.{note}"}


# ── what the reader got ──────────────────────────────────────────────────────

OUTCOME_NAMES = {
    "read": "Read live, with usable content",
    "incomplete": "Answered, but with incomplete content",
    "denied": "Access denied (HTTP 401 or 403)",
    "rate_limited": "Rate limited (HTTP 429)",
    "server_error": "Server error (HTTP 5xx)",
    "robots": "Disallowed by robots.txt",
    "rendering": "No content without JavaScript",
    "network": "Timed out or could not connect",
    "challenge": "Bot check or sign-in",
    "not_found": "Not found (HTTP 404 or 410)",
    "other": "Not established",
}
#: Outcomes that say our reader was stopped, as opposed to the page being wrong.
STOPPED = frozenset({"denied", "rate_limited", "server_error", "robots", "rendering", "network", "challenge", "other"})


def crawl_outcome(*, status: int | None, challenged: bool = False, empty: bool = False, error: str | None = None, robots: bool = False) -> str:
    """One category for what came back. `error` is the reader's own failure text when nothing came back."""
    if error:
        text = error.lower()
        return "network" if any(w in text for w in ("too long", "timeout", "could not be fetched", "connect", "redirects too many")) else "other"
    if robots:
        return "robots"
    if challenged:
        return "challenge"
    if status in (401, 403):
        return "denied"
    if status == 429:
        return "rate_limited"
    if status in (404, 410):
        return "not_found"
    if status is not None and status >= 500:
        return "server_error"
    if empty:
        return "rendering"
    if status is not None and status < 400:
        return "read"
    return "other"


def technical_finding(outcome: str, *, impressions: int, window_to: str | None) -> dict[str, Any]:
    """What a stopped read does and does not show.

    Our reader being stopped is not Google being stopped. Search Console impressions inside the window are
    the one independent sign held here that Google was showing the page.
    """
    seen = impressions > 0
    google = (
        f"Search Console records {impressions:,} impressions for this page in the window ending {window_to}, so Google was showing it."
        if seen else "No Search Console impressions for this page in the window, so there is no independent sign that Google can read it."
    )
    if outcome in ("server_error", "network"):
        kind = "Potential technical issue requiring verification"
        impact = "A server that errors or times out for one reader may do so for others. Whether it does for Google has not been established."
    elif outcome == "robots":
        kind = "Potential technical issue requiring verification" if not seen else "Tool-specific crawl limitation"
        impact = "robots.txt stops our reader. Whether the same rule applies to Googlebot depends on which user agents it names."
    elif seen:
        kind = "Tool-specific crawl limitation"
        impact = "The restriction stops reliable automated analysis of the page. Search engine impact has not been established, and the Search Console data points against it."
    else:
        kind = "Insufficient evidence"
        impact = "The restriction stops reliable automated analysis of the page. Search engine impact has not been established."
    return {"classification": kind, "impact": impact, "google": google}


# ── how far a change reaches ─────────────────────────────────────────────────

PAGE_SPECIFIC, TEMPLATE_WIDE, SITEWIDE, NEW_CONTENT = "page-specific", "template-wide", "sitewide", "new supporting content"
#: Parts that change a page's structure, where a shared template matters.
_STRUCTURAL = frozenset({"A-1", "S-2", "P-1", "PC-1"})
_MARKUP = frozenset({"V-7"})
_ELSEWHERE = frozenset({"S-4", "V-4"})


def template_of(url: str, kind: str, site_urls: Iterable[str] | None) -> dict[str, Any]:
    """Whether the page looks like one of many built from one template, judged from the crawl's addresses.

    `site_urls` is None when there is no crawl: the answer is then "unverified", never "free to restructure".
    """
    if site_urls is None:
        return {"shared": None, "peers": 0, "pattern": None, "basis": "unverified", "note": "No site crawl to compare against, so whether this page shares a template is unverified."}
    parts = [p for p in urlsplit(url).path.split("/") if p]
    if len(parts) < 2:
        return {"shared": False, "peers": 0, "pattern": None, "basis": "inferred", "note": "The page sits at the top of the site, so it is treated as its own layout."}
    prefix = "/" + "/".join(parts[:-1]) + "/"
    peers = sum(1 for u in site_urls if (urlsplit(u).path or "/").startswith(prefix) and u != url)
    shared = peers >= 4
    return {
        "shared": shared, "peers": peers, "pattern": prefix, "basis": "inferred",
        "note": (
            f"{peers} other pages sit under {prefix}, so this page very likely shares their template. Inferred from addresses, not confirmed."
            if shared else f"Only {peers} other pages sit under {prefix}, so no shared template is assumed."
        ),
    }


def scope_of(part_id: str, template: dict[str, Any]) -> dict[str, str]:
    """Where a part's change lands and what to watch for."""
    if part_id == "SC-1":
        return {"scope": NEW_CONTENT, "note": "A separate page. The page this action started from is not restructured."}
    if part_id == "TI-1":
        return {"scope": SITEWIDE, "note": "Access rules usually apply to the whole site or host."}
    if part_id in _ELSEWHERE:
        return {"scope": PAGE_SPECIFIC, "note": "Made on the linking pages' own content, one page at a time."}
    if part_id in _MARKUP:
        if template["shared"]:
            return {"scope": TEMPLATE_WIDE, "note": f"Markup usually comes from the template, so this may affect the {template['peers']} pages under {template['pattern']}. Check before changing it."}
        return {"scope": PAGE_SPECIFIC, "note": "Whether the markup comes from a shared template is unverified." if template["shared"] is None else "No shared template is assumed."}
    if part_id in _STRUCTURAL:
        if template["shared"]:
            return {"scope": PAGE_SPECIFIC, "note": f"Use this page's own content fields. Do not change the template: it is shared by about {template['peers']} pages under {template['pattern']}."}
        if template["shared"] is None:
            return {"scope": PAGE_SPECIFIC, "note": "Template constraint unverified: confirm the page can be edited on its own before restructuring it."}
        return {"scope": PAGE_SPECIFIC, "note": "No shared template is assumed."}
    return {"scope": PAGE_SPECIFIC, "note": "Changes this page's own title, description or wording."}


# ── the gate ─────────────────────────────────────────────────────────────────

PUBLISH, VERIFY, REJECT = "publish", "needs_verification", "reject"


def validate(*, intent: dict[str, Any], page: dict[str, Any], fit: dict[str, Any], evidence: dict[str, Any], template: dict[str, Any], parts: list[dict[str, Any]], rerouted: bool, duplicate_of: str | None = None) -> dict[str, Any]:
    """Ten questions, each answered pass, unverified or fail, and what to do with the action as a result.

    A failed critical check rejects the action. An unverified one lets it through marked for verification.
    Nothing here raises a weak action to fill a quota: an action with no parts is rejected.
    """
    investigation = any(p["id"] == "TI-1" for p in parts)
    checks: list[dict[str, str]] = []

    def add(key: str, question: str, state: str, detail: str, critical: bool = False) -> None:
        checks.append({"key": key, "question": question, "state": state, "detail": detail, "critical": "yes" if critical else "no"})

    def tri(ok: bool | None) -> str:
        return "unverified" if ok is None else "pass" if ok else "fail"

    add("intent", "Is the search's intent understood?", "pass" if is_read(intent) and intent["confidence"] in ("high", "medium") else "unverified",
        (f"{intent['name']}, {intent['confidence']} confidence, read from the results page of {intent.get('serp_date')}." if is_read(intent) else f"{intent['name']}. {intent.get('uncertainty') or ''}".strip()))
    add("page_type", "Is the page's type known?", "pass" if page["type"] != OTHER else "unverified", page["name"] + (f", from {' and '.join(page['basis'])}" if page["basis"] else "") + ".")
    purpose_ok = True if investigation or rerouted else None if fit["level"] == UNVERIFIED else fit["level"] != LOW
    add("purpose", "Does the action match the page's purpose?", tri(purpose_ok), "The work was routed to the kind of page that ranks for the search." if rerouted else fit["why"], critical=True)
    add("destination", "Is the page the right destination for the search?", "pass" if rerouted or investigation else tri(None if fit["level"] == UNVERIFIED else fit["level"] != LOW),
        "The page is kept as the place the search was noticed; the work goes elsewhere." if rerouted else fit["why"], critical=True)
    add("template", "Does the action respect template constraints?", "unverified" if template["shared"] is None else "pass", template["note"])
    enough = evidence["sufficient"]
    add("evidence", "Is the evidence sufficient and current?", "pass" if enough and not evidence["unverified"] else "unverified" if enough or investigation else "fail",
        evidence["summary"], critical=True)
    add("implementable", "Can a team member carry it out?", "pass" if parts and all(p.get("steps") for p in parts) else "fail", f"{len(parts)} part{'s' if len(parts) != 1 else ''}, each with steps." if parts else "Nothing to do was found.", critical=True)
    add("benefit", "Is there a plausible benefit?", "pass" if parts else "fail", "Search, AI visibility, conversion or technical reliability, as stated per part. No figure is forecast.")
    add("duplicate", "Is it a duplicate?", "fail" if duplicate_of else "pass", f"The same page and topic are already planned: {duplicate_of}." if duplicate_of else "No other action for this page and topic was found.", critical=True)
    add("specific", "Is it specific enough to execute?", "pass" if parts and all(len(p.get("steps") or []) >= 1 for p in parts) else "fail", "Each part names what to change and where.")

    failed = [c for c in checks if c["state"] == "fail" and c["critical"] == "yes"]
    unverified = [c for c in checks if c["state"] == "unverified"]
    verdict = REJECT if failed else VERIFY if investigation or any(c["critical"] == "yes" for c in unverified) else PUBLISH
    return {
        "verdict": verdict, "checks": checks,
        "summary": (
            "Not offered: " + "; ".join(c["detail"] for c in failed) if failed
            else "Offered, with points to verify first: " + "; ".join(c["question"] for c in unverified) if verdict == VERIFY
            else "Every check passed" + (f", {len(unverified)} left unverified" if unverified else "") + "."
        ),
    }


# ── choosing between candidates ──────────────────────────────────────────────

_TIER = {HIGH: 0, MEDIUM: 1, UNVERIFIED: 2, LOW: 3}


def select(candidates: list[dict[str, Any]], limit: int) -> dict[str, list[dict[str, Any]]]:
    """Eligibility first, score second, and never a weak candidate to make up the number.

    A candidate is `{..., "score": number, "fit": level, "evidence_ok": bool}`. A low fit or missing evidence
    excludes it, with the reason. Fewer than `limit` may come back.
    """
    chosen: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for c in sorted(candidates, key=lambda c: (_TIER.get(c.get("fit", UNVERIFIED), 2), -float(c.get("score") or 0))):
        if c.get("fit") == LOW:
            excluded.append({**c, "excluded_because": "The page does not suit the search's intent, however many impressions it has."})
        elif c.get("evidence_ok") is False:
            excluded.append({**c, "excluded_because": "The page could not be read and no earlier copy of it is held."})
        elif len(chosen) < limit:
            chosen.append(c)
    return {"chosen": chosen, "excluded": excluded}


# ── why a reviewer turned an action down ─────────────────────────────────────

REJECTION_REASONS = {
    "wrong_intent": "Wrong search intent",
    "wrong_page_type": "Wrong page type",
    "wrong_target": "Wrong target URL",
    "template_constraint": "Template constraint",
    "insufficient_evidence": "Insufficient evidence",
    "crawl_misread": "Incorrect crawl interpretation",
    "duplicate": "Duplicate recommendation",
    "low_value": "Low business value",
}
