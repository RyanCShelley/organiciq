"""Things worth doing that the catalog's rules cannot yet confirm.

The catalog's Visibility rules are strict on purpose: each fires only when the data that proves
it is present (a declared owner page, the SERP's features, the site-wide link crawl). For a page
read on demand most of that data is absent, so most pages return "no rule fires", which is true
and not very useful.

This layer says what is still worth looking at, using only what a page read and Search Console
do know. Every item is labelled *unconfirmed* and names the missing data that would turn it into
a rule. Nothing here is a prescription, nothing is sent to the plan, and the catalog is untouched,
so the live tool's rules do not change.

Suggestions never invent copy. They quote what the page says now and what people search, and
leave the wording to a person.
"""

from __future__ import annotations

from typing import Any

from app.decisions.catalog import PageFacts, _mentions
from app.decisions.ctr_curve import expected_ctr_percent
from app.ingestion.crawler.parse import ParsedPage
from app.services.target_signals import _is_question

_STOP = frozenset("a an and are as at be by for from how in is it of on or the to what when where which who why with your".split())


def _tokens(text: str) -> set[str]:
    import re

    return {t for t in re.findall(r"[^\W_]+", text.lower()) if len(t) >= 2 and t not in _STOP}


def _item(id_: str, title: str, why: str, steps: list[str], needs: str, evidence: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": id_,
        "title": title,
        "why": why,
        "steps": steps,
        "needs_to_confirm": needs,
        "confidence": "unconfirmed",
        "evidence": evidence or [],
    }


def suggest(
    *,
    search: str,
    url: str,
    row: dict[str, Any],
    parsed: ParsedPage,
    facts: PageFacts,
    evidence: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """`{suggestions: [...], skipped: [{id, name, reason}]}`."""
    out: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    wanted = _tokens(search)
    page_queries = evidence.get("page_queries") or []

    # S-6: more than one page shows for the search.
    competing = int(evidence.get("competing_pages") or 0)
    if competing > 1:
        out.append(
            _item(
                "S-6",
                f"Decide which page should own “{search}”",
                f"{competing} pages of the site show for this search, so they split its impressions and each ranks lower than one page might.",
                [
                    f"Pick the page that should rank for “{search}”.",
                    "Point the other pages at it with an in-content link, and stop repeating the same target phrase in their titles.",
                ],
                "A declared owner page for the search (rule V-6), which comes with the Topic Hub mapping.",
                [f"{competing} pages show for this search in Search Console"],
            )
        )

    # S-1: phrasing people search that the title and main heading do not use.
    related = [
        q for q in page_queries
        if q["query"] != " ".join(search.lower().split())
        and len(_tokens(q["query"]) & wanted) >= min(2, len(wanted))
        and q["impressions"] >= 20
    ]
    missing = [q for q in related if not _mentions(q["query"], parsed.title) and not _mentions(q["query"], parsed.h1)][:3]
    if missing:
        slug = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1].replace("-", " ").lower()
        steps = [
            f"“{q['query']}”: {q['impressions']:,} impressions at position {q['position']}, in neither the title nor the main heading."
            for q in missing
        ]
        steps.append(f"Today the title reads “{parsed.title}” and the main heading “{parsed.h1}”.")
        steps.append("Work the closest natural phrasing into the title, and into the main heading if it reads well. Do not stuff it.")
        top = missing[0]["query"]
        in_slug = all(t in slug for t in _tokens(top))
        steps.append(
            f"The URL ({url.split('/')[-1]}) {'already carries' if in_slug else 'does not carry'} the words of “{top}”. "
            "Changing a live address needs a redirect, so treat the URL as a note and not a first move."
        )
        out.append(
            _item(
                "S-1",
                "Use the phrasing people actually search",
                "The page already ranks for these longer searches. Saying them in the title or heading is the cheapest way to line the page up with them.",
                steps,
                "A person's judgment that the wording reads naturally. No data is missing.",
                [f"Page queries from Search Console, {len(page_queries)} with impressions"],
            )
        )

    # S-5: top-three position, enough impressions, click-through under the benchmark.
    impressions, clicks, position = row["impressions"], row["clicks"], float(row["position"])
    if position <= 3.5 and impressions >= 100:
        actual = clicks / impressions * 100
        expected = expected_ctr_percent(position)
        if actual < 0.9 * expected:
            out.append(
                _item(
                    "S-5",
                    "Reread the title and description as the searcher",
                    f"Click-through is {actual:.1f}% against {expected:.1f}% expected at position {position:.1f}. At this position a gap is usually the snippet, not the ranking.",
                    [
                        f"Search “{search}” and read the result as a shopper would.",
                        f"Title now: “{parsed.title}”.",
                        f"Description now: “{parsed.description or '(none)'}”.",
                        "Ask whether they say this page is the answer, and what a competitor's snippet promises that this one does not.",
                    ],
                    "Whether SERP features (an AI answer, shopping results) sit above the result and take clicks that wording cannot win back. Not pulled yet.",
                    [f"{impressions:,} impressions, {clicks:,} clicks"],
                )
            )

    # S-3: nothing on the page an answer engine can lift whole.
    if facts.sections and not any(s.extractable for s in facts.sections):
        out.append(
            _item(
                "S-3",
                "Give an answer engine something to lift",
                f"None of the page's {len(facts.sections)} headed sections holds a table, a bulleted summary or a stat block, which are the shapes snippets and AI answers quote.",
                [
                    f"Near the top, add a short table or bulleted summary of what someone searching “{search}” wants to compare.",
                    "Keep it factual and true to the page, so what is lifted is accurate.",
                ],
                "The SERP's features for this search, to know whether a snippet or AI answer is being shown at all. Not pulled yet.",
                [f"{len(facts.sections)} sections read, none with a table, list or stat"],
            )
        )

    # S-2: an FAQ built from questions people really ask. (An existing FAQ without markup is V-7.)
    if not facts.has_faq_section:
        questions = [q for q in page_queries if _is_question(q["query"])][:5]
        if questions:
            out.append(
                _item(
                    "S-2",
                    "Add a short FAQ from real questions",
                    "The page has no FAQ, and it already gets impressions for questions people type.",
                    [f"“{q['query']}” ({q['impressions']:,} impressions)" for q in questions]
                    + [
                        "Answer each in one to three sentences on the page, in the words you would use to a customer.",
                        "Then mark it up as FAQPage (rule V-7 will pick it up once the section exists).",
                    ],
                    "Whether an AI answer or featured snippet appears for these questions. Not pulled yet.",
                    [f"{len(questions)} question-shaped searches for this page"],
                )
            )
        else:
            skipped.append(
                {
                    "id": "S-2",
                    "name": "Add a short FAQ",
                    "reason": "No question-shaped search shows for this page, so there is nothing real to base an FAQ on.",
                }
            )

    # S-4: other pages on the same topic that could link here.
    donors = evidence.get("donors") or []
    if donors:
        out.append(
            _item(
                "S-4",
                "Link here from pages on the same topic",
                "These pages already show for searches on this topic, so a link from them is relevant and carries readers.",
                [
                    f"{d['url']} (shows for “{d['query']}”, {d['impressions']:,} impressions): add an in-content link to this page where it reads naturally."
                    for d in donors[:3]
                ]
                + ["Check each page does not already link here first."],
                "The site-wide link crawl, to see which of these already link here and how many links this page has against the site's median.",
                [f"{len(donors)} topical pages found in Search Console"],
            )
        )
    else:
        skipped.append(
            {
                "id": "S-4",
                "name": "Add internal links",
                "reason": "No other page shows for searches on this topic, so no natural source for a link was found.",
            }
        )

    return {"suggestions": out, "skipped": skipped}
