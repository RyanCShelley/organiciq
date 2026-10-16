"""Say why a failing branch produced no action.

An empty slot read "No qualifying target left in a failing branch (visibility,
traffic)" and nothing more, which is true and sends nobody anywhere. Corvant's
September had Visibility failing on a page no term was mapped to, Traffic
failing on 58 missed clicks against 72 earned, and five empty slots: the reasons
were a keyword map with nothing in it and a traffic action that only reaches the
top three results, and neither was on the page.

Plain counts from the same readings the tests used. Nothing here decides anything.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.catalog import MIN_IMPRESSIONS, SNIPPET_MAX_POSITION
from app.models.decision import KeywordTarget
from app.models.seranking import FactSerKeyword
from app.services.triage_signals import page_shortfalls


def traffic_gap(shortfalls: list[dict]) -> dict:
    """Where the missed clicks are, and how much of it the traffic actions can reach.

    T-1 rewrites a snippet and only fires for a page in the top three with enough
    impressions for the curve to mean something. A page lower down earns fewer
    clicks than its position "should" for reasons a snippet does not touch.
    """
    top = thin = below = 0.0
    top_n = thin_n = below_n = 0
    for row in shortfalls:
        missed = row["missed_clicks"]
        if missed <= 0:
            continue
        position = row["position"]
        if position is not None and position <= SNIPPET_MAX_POSITION:
            if row["impressions"] >= MIN_IMPRESSIONS:
                top, top_n = top + missed, top_n + 1
            else:
                thin, thin_n = thin + missed, thin_n + 1
        else:
            below, below_n = below + missed, below_n + 1
    return {
        "reachable": {"pages": top_n, "missed": round(top)},
        "too_few_impressions": {"pages": thin_n, "missed": round(thin)},
        "below_top_three": {"pages": below_n, "missed": round(below)},
    }


def keyword_map_counts(db: Session, client_id: UUID) -> tuple[int, int]:
    """Tracked keywords, and how many of them have a confirmed page mapped."""
    tracked = {
        (k or "").strip().lower()
        for (k,) in db.query(FactSerKeyword.keyword).filter(FactSerKeyword.client_id == client_id)
    }
    mapped = {
        (t.keyword or "").strip().lower()
        for t in db.query(KeywordTarget).filter(
            KeywordTarget.client_id == client_id,
            KeywordTarget.source == "confirmed",
        )
        if (t.target_url or "").strip()
    }
    return len(tracked), len(tracked & mapped)


def empty_plan_note(
    db: Session,
    client_id: UUID,
    *,
    failing: list[str],
    gsc_period: tuple[date, date] | None,
) -> str:
    """One or two sentences naming what is behind the empty slots."""
    parts: list[str] = []
    if "visibility" in failing:
        tracked, mapped = keyword_map_counts(db, client_id)
        if tracked:
            parts.append(
                f"Visibility can only act on terms mapped to a page, and {mapped} of "
                f"{tracked} tracked terms are. Map the rest in the keyword map and "
                "re-run."
            )
        else:
            parts.append("Visibility has no tracked keywords to act on.")
    if "traffic" in failing and gsc_period is not None:
        gap = traffic_gap(page_shortfalls(db, client_id, gsc_period))
        total = sum(v["missed"] for v in gap.values())
        if total:
            r, t, b = gap["reachable"], gap["too_few_impressions"], gap["below_top_three"]
            parts.append(
                f"Traffic: of {total} clicks missed, {r['missed']} sit on {r['pages']} "
                f"top-three pages a snippet rewrite can reach, {t['missed']} are on "
                f"{t['pages']} top-three pages with under {MIN_IMPRESSIONS:.0f} "
                f"impressions, and {b['missed']} are on {b['pages']} pages ranking below "
                "the top three, which no traffic action covers: those need better "
                "rankings, not a new snippet."
            )
    return " ".join(parts)
