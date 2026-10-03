"""Why a listing is not earning its clicks, and what to write instead.

Playbook 4. The old finding said "rewrite the title and description against
what is actually winning the click", which names neither what is wrong with
the title nor what the new one should say.

Two things the playbook asks for are not in our data: whether Google is
rewriting the title, which needs the SERP's rendered title, and what the
competing titles carry that ours does not. Both become named human checks.
What is left is enough to draft a replacement, and drafting one is the
difference between a finding and an instruction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.decisions.prescription import Prescription, Step

#: Google truncates around here, and the query has to land before it.
TITLE_MAX_CHARS = 60
QUERY_WITHIN_CHARS = 40
DESCRIPTION_MAX_CHARS = 155


@dataclass(frozen=True)
class CtrSignals:
    page_url: str
    top_query: str
    impressions: float
    clicks: float
    ctr_percent: float
    expected_ctr_percent: float
    recoverable_clicks: float
    title: str | None
    description: str | None
    brand: str | None = None
    ai_overview: bool = False


def draft_title(query: str, brand: str | None, existing: str | None) -> str:
    """A title that leads with the query and still reads like a title.

    Deliberately plain: the engine is not writing copy, it is showing the
    shape the copy has to take so a person can improve on something rather
    than start from a rule.
    """
    head = query.strip()
    head = head[:1].upper() + head[1:]
    suffix = f" | {brand}" if brand else ""
    room = TITLE_MAX_CHARS - len(head) - len(suffix)
    qualifier = ""
    if existing and room > 12:
        # Reuse the most specific-looking fragment of the current title
        # rather than inventing a claim the page may not support.
        brand_words = {w for w in re.findall(r"[a-z]+", (brand or "").lower())}
        for part in re.split(r"[|–—\-]", existing):
            part = part.strip()
            words = set(re.findall(r"[a-z]+", part.lower()))
            if not part or len(part) > room - 3:
                continue
            # Skip the brand itself and anything the head already says, or
            # the title repeats itself inside sixty characters.
            if (words & brand_words) or part.lower() in head.lower():
                continue
            qualifier = f" — {part}"
            break
    return f"{head}{qualifier}{suffix}"[:TITLE_MAX_CHARS]


def classify_ctr_gap(signals: CtrSignals) -> Prescription:
    evidence = {
        "top_query": signals.top_query,
        "impressions": round(signals.impressions),
        "clicks": round(signals.clicks),
        "ctr_percent": round(signals.ctr_percent, 2),
        "expected_ctr_percent": round(signals.expected_ctr_percent, 2),
        "ai_overview_present": signals.ai_overview,
        "current_title": signals.title,
    }

    query_in_title = bool(signals.title) and signals.top_query.lower() in (
        signals.title or ""
    ).lower()
    query_position = (
        (signals.title or "").lower().find(signals.top_query.lower())
        if query_in_title
        else -1
    )
    buried = query_in_title and query_position > QUERY_WITHIN_CHARS

    steps: list[Step] = []
    if not query_in_title or buried:
        proposed = draft_title(signals.top_query, signals.brand, signals.title)
        why = (
            "the title does not contain the query at all"
            if not query_in_title
            else f"the query starts {query_position} characters in, past where Google truncates"
        )
        steps.append(
            Step(
                f"Rewrite the title to lead with “{signals.top_query}”",
                target=signals.page_url,
                detail=f"Currently “{signals.title}” — {why}. "
                f"Try: “{proposed}”",
            )
        )
    else:
        steps.append(
            Step(
                "Add one specific to the title: a number, an audience or an outcome",
                target=signals.page_url,
                detail=f"“{signals.title}” already leads with the query, so the "
                "gap is that it reads like every other result.",
            )
        )

    steps.append(
        Step(
            "Rewrite the meta description to answer the query in its first sentence",
            target=signals.page_url,
            detail=f"Proof in the second, a call to action third, "
            f"{DESCRIPTION_MAX_CHARS} characters. Currently "
            + (f"“{signals.description}”" if signals.description else "empty")
            + ".",
        )
    )

    if signals.ai_overview:
        steps.append(
            Step(
                "Work the AI Overview as well as the listing",
                target=signals.page_url,
                detail="An AI Overview sits above this result and roughly halves what "
                "position one earns. A better title cannot win back a click the answer "
                "already satisfied, so the page also needs to be citable.",
            )
        )

    steps.append(
        Step(
            "Check whether Google is rewriting this title, and what the results above "
            "it carry that this one does not",
            target=signals.page_url,
            detail="The SERP's rendered titles are not stored, so this is the one "
            "comparison our data cannot make.",
            human=True,
        )
    )

    return Prescription(
        cause="ctr_loss",
        evidence=evidence,
        steps=steps,
        expected_impact=f"about {signals.recoverable_clicks:,.0f} clicks a period",
        verify_metric="ctr_top5_queries",
        verify_after_days=28,
    )
