"""Read a search's intent from its results page, the way a person doing the search-intent exercise would.

Intent is what the searcher is trying to get done, and the search engine has already answered that in what it
chose to show. So three things are looked at on the page that was actually pulled:

1. what type of content ranks (product pages, collections, articles, video, local listings);
2. what style it is in (lists, how-to, comparisons, reviews, guides);
3. which features show (a product carousel, a featured snippet, a local pack).

A keyword tool's label is somebody else's guess and never decides: one called "natural sunscreen" informational
while its results page was product listings. Labels are passed in only so a disagreement can be shown.

A model does the reading, because "10 Best…", "…vs…" and a shop's collection title are easy for a reader and
brittle as rules. What it returns is checked here: only the allowed intents and needs, evidence required for
each, and "insufficient" kept as an answer. With no results page there is no reading at all, and nothing that
depends on intent is recommended (see `not_read`).

The consumer need (help me, reassure me, educate me, surprise me, impress me, thrill me) is a second layer over
the intent, for messaging and proof. It is assigned only on evidence, and marked as observed or inferred.
"""

from __future__ import annotations

import json
from typing import Any, Callable

INFORMATIONAL, NAVIGATIONAL, COMMERCIAL, TRANSACTIONAL, LOCAL, MIXED = "informational", "navigational", "commercial", "transactional", "local", "mixed"
NOT_READ, INSUFFICIENT = "not_read", "insufficient"
INTENTS = (INFORMATIONAL, NAVIGATIONAL, COMMERCIAL, TRANSACTIONAL, LOCAL, MIXED)
INTENT_NAMES = {
    INFORMATIONAL: "Informational", NAVIGATIONAL: "Navigational", COMMERCIAL: "Commercial", TRANSACTIONAL: "Transactional",
    LOCAL: "Local", MIXED: "Mixed", NOT_READ: "Intent not read — No SERP available", INSUFFICIENT: "Intent not settled by the SERP",
}
#: What the searcher is trying to do, in one line, when the model gives none.
GOALS = {
    INFORMATIONAL: "learn about the topic", NAVIGATIONAL: "get to a particular site or page", COMMERCIAL: "compare options before buying",
    TRANSACTIONAL: "find and buy the thing", LOCAL: "find a nearby business or service",
}
NEEDS = {
    "help": "Help me", "reassure": "Reassure me", "educate": "Educate me", "surprise": "Surprise me", "impress": "Impress me", "thrill": "Thrill me",
}
CONTENT_TYPES = ("product page", "category or collection page", "service page", "local listing", "article or blog post", "guide or resource", "video", "forum or community", "homepage", "tool", "news", "other")
CONTENT_STYLES = ("list", "how-to", "question and answer", "comparison", "product review", "guide", "case study", "research or stats", "news", "opinion", "product listing", "none")
#: Features that carry no intent of their own: they show on results of every kind.
_NEUTRAL = frozenset({"organic", "paid", "related_searches", "people_also_search", "ai_overview", "knowledge_graph", "perspectives", "discussions_and_forums"})

PROMPT = """You are reading one Google results page to say what the searcher is trying to accomplish.
Judge ONLY from the results page below. Do not use what the keyword could mean in general, and do not guess past the evidence.

Search: {search}
Market: {market}

Features on the page (Google's element types, in the order they appear):
{features}

Top organic results:
{results}

Keyword-tool labels (for reference only; they never decide, and may be wrong):
{labels}

Work through it in this order:
1. Content type of each organic result. Use only: {types}.
2. Content style of each. Use only: {styles}.
3. Which features bear on intent (for example a product carousel or popular products means shopping; a local pack means a nearby business; a featured snippet or how-to box means an explanation). People-also-ask, AI overviews, ads and knowledge panels appear on every kind of page and are weak evidence.
4. The primary intent, and a secondary one only if the page gives real evidence of a second purpose. If the two compete and neither clearly leads, set "mixed" to true.

Intents:
- informational: wants to understand or learn something.
- navigational: wants a particular site, brand or page.
- commercial: is researching options before buying (best, top, reviews, comparisons).
- transactional: wants to find and buy, book or order the thing now.
- local: geographic proximity or finding a nearby business or service is central.
Mixed is not a sixth choice for "primary": name the two intents as primary and secondary and set "mixed" to true.
If the evidence does not settle it, set "primary" to "insufficient" and say why. Do not force an answer.

Then, only if the page gives evidence for it, one consumer need:
help (practical problem-solving), reassure (trust, safety, simplicity), educate (understanding, informed decisions), surprise (novelty, discovery), impress (aspiration, status), thrill (excitement, adventure).
Mark it "observed" when results or features show it directly (for example safety and ingredient claims in ranking titles), "inferred" when you are reasoning from the kind of product. If there is no real evidence, use null.

Return ONLY this JSON:
{{
  "primary": "informational|navigational|commercial|transactional|local|insufficient",
  "secondary": "informational|navigational|commercial|transactional|local or null",
  "mixed": true or false,
  "confidence": "high|medium|low",
  "searcher_goal": "one plain sentence: what the searcher is trying to get done",
  "results": [{{"rank": 1, "content_type": "...", "content_style": "..."}}],
  "evidence": ["short observations from the page, each naming what was seen, e.g. '7 of 10 results are product or collection pages'"],
  "uncertainty": "what is unclear or could not be seen, or null",
  "label_disagreement": "one sentence if a keyword-tool label disagrees with the page, or null",
  "consumer_need": {{"need": "help|reassure|educate|surprise|impress|thrill", "basis": "observed|inferred", "evidence": "what on the page supports it"}} or null,
  "content_to_match": "one or two sentences: what kind of content, in what style, matches this intent on this results page"
}}"""


def not_read(reason: str = "No results page is held for this search.") -> dict[str, Any]:
    """The reading when there is no results page. Nothing that depends on intent may be recommended from it."""
    return {
        "intent": NOT_READ, "name": INTENT_NAMES[NOT_READ], "primary": None, "secondary": None, "confidence": "none", "read": False,
        "searcher_goal": None, "evidence": [], "uncertainty": reason, "content_types": {}, "content_styles": {}, "features": [],
        "label_disagreement": None, "consumer_need": None, "content_to_match": None, "serp_date": None, "labels": [], "ranked": [],
    }


def _tally(rows: list[dict[str, Any]], key: str, allowed: tuple[str, ...]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "").strip().lower()
        if value in allowed and value != "none":
            out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _ranked(results: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The ranking results with the type and style the reading gave each: who is winning, one line apiece."""
    by_rank = {int(r["rank"]): r for r in rows if str(r.get("rank") or "").isdigit() or isinstance(r.get("rank"), int)}
    out = []
    for r in results[:10]:
        seen = by_rank.get(int(r.get("rank") or 0), {})
        kind, style = str(seen.get("content_type") or "").lower(), str(seen.get("content_style") or "").lower()
        out.append({
            "rank": r.get("rank"), "url": r.get("url"), "domain": r.get("domain"), "title": r.get("title"),
            "content_type": kind if kind in CONTENT_TYPES else None, "content_style": style if style in CONTENT_STYLES and style != "none" else None,
        })
    return out


def _clean(raw: Any, *, item_types: list[str], serp_date: str | None, labels: list[str], results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The model's answer, held to what is allowed. Anything outside it is dropped, not repaired into a claim."""
    if not isinstance(raw, dict):
        raise ValueError("the reading was not an object")
    primary = str(raw.get("primary") or "").strip().lower()
    secondary = str(raw.get("secondary") or "").strip().lower() or None
    if primary not in GOALS and primary != INSUFFICIENT:
        raise ValueError(f"the reading named an intent that is not one of ours: {primary!r}")
    if secondary not in GOALS or secondary == primary:
        secondary = None
    evidence = [" ".join(str(e).split()) for e in (raw.get("evidence") or []) if str(e).strip()][:8]
    if primary != INSUFFICIENT and not evidence:
        # An intent with nothing seen to support it is a guess, and a guess is not a reading.
        primary = INSUFFICIENT
    rows = [r for r in (raw.get("results") or []) if isinstance(r, dict)]
    need = raw.get("consumer_need")
    if not (isinstance(need, dict) and str(need.get("need") or "").lower() in NEEDS and str(need.get("basis") or "").lower() in ("observed", "inferred") and str(need.get("evidence") or "").strip()):
        need = None
    else:
        key = str(need["need"]).lower()
        need = {"need": key, "name": NEEDS[key], "basis": str(need["basis"]).lower(), "evidence": " ".join(str(need["evidence"]).split())}
    confidence = str(raw.get("confidence") or "").lower()
    # Mixed needs two named intents; "mixed" with only one is just that one.
    intent = MIXED if raw.get("mixed") is True and secondary and primary != INSUFFICIENT else primary
    return {
        "intent": intent, "name": INTENT_NAMES[intent], "primary": None if primary == INSUFFICIENT else primary, "secondary": secondary,
        "confidence": confidence if confidence in ("high", "medium", "low") and primary != INSUFFICIENT else "none" if primary == INSUFFICIENT else "low",
        "read": primary != INSUFFICIENT,
        "searcher_goal": " ".join(str(raw.get("searcher_goal") or "").split()) or (f"The searcher wants to {GOALS[primary]}." if primary in GOALS else None),
        "evidence": evidence,
        "uncertainty": " ".join(str(raw.get("uncertainty") or "").split()) or None,
        "content_types": _tally(rows, "content_type", CONTENT_TYPES),
        "content_styles": _tally(rows, "content_style", CONTENT_STYLES),
        "features": [t for t in item_types if t not in _NEUTRAL],
        "label_disagreement": " ".join(str(raw.get("label_disagreement") or "").split()) or None,
        "consumer_need": need,
        "content_to_match": " ".join(str(raw.get("content_to_match") or "").split()) or None,
        "serp_date": serp_date, "labels": labels,
        "ranked": _ranked(results or [], rows),
    }


def read(
    search: str,
    *,
    item_types: list[str] | None,
    results: list[dict[str, Any]] | None,
    serp_date: str | None = None,
    labels: list[str] | None = None,
    market: str = "us",
    ask: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """The reading for one search. `ask(prompt) -> text` is the model call, passed in so this stays testable.

    No results page, or one pulled before ranking results were kept, gives `not_read`: there is nothing to read.
    A model failure or an answer that does not hold up gives `insufficient` with the reason, never a guess.
    """
    labels = [str(x) for x in (labels or []) if x]
    if item_types is None:
        return not_read()
    if not results:
        return not_read("The results page held for this search was pulled before ranking results were kept, so there is nothing to read.")
    if ask is None:
        from app.schema_tools import llm

        ask = lambda prompt: llm.call("quick", prompt, max_tokens=1800)[0]  # noqa: E731
    listed = "\n".join(
        f"{r.get('rank')}. {r.get('title') or '(no title)'}\n   {r.get('url')}\n   {r.get('snippet') or ''}".rstrip() for r in results[:10]
    )
    prompt = PROMPT.format(
        search=search, market=market, features=", ".join(item_types) or "(none)", results=listed,
        labels=", ".join(labels) or "(none held)", types=", ".join(CONTENT_TYPES), styles=", ".join(CONTENT_STYLES),
    )
    try:
        from app.schema_tools.llm import extract_json

        return _clean(extract_json(ask(prompt)), item_types=list(item_types), serp_date=serp_date, labels=labels, results=list(results))
    except Exception as exc:  # The model not answering, or answering out of bounds, leaves the intent unsettled.
        out = not_read(f"The results page could not be read ({type(exc).__name__}: {str(exc)[:160]}).")
        out.update(intent=INSUFFICIENT, name=INTENT_NAMES[INSUFFICIENT], serp_date=serp_date, labels=labels, features=[t for t in item_types if t not in _NEUTRAL])
        return out


def describe(reading: dict[str, Any]) -> str:
    """One line for a task's evidence."""
    if not reading.get("read"):
        return f"{reading['name']}. {reading.get('uncertainty') or ''}".strip()
    second = f", secondary {INTENT_NAMES[reading['secondary']].lower()}" if reading.get("secondary") else ""
    if reading["intent"] == MIXED:
        second = f" ({INTENT_NAMES[reading['primary']].lower()} and {INTENT_NAMES[reading['secondary']].lower()})"
    when = f" on the results page of {reading['serp_date']}" if reading.get("serp_date") else ""
    return f"Search intent: {reading['name']}{second} ({reading['confidence']} confidence){when}. " + " ".join(e.rstrip(".") + "." for e in reading["evidence"][:3])


def dump(reading: dict[str, Any]) -> str:
    return json.dumps(reading, ensure_ascii=False)
