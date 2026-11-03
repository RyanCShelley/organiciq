"""Content gaps: searches people make that the site has no page for, ranked by the searches a page could compete for.

Three sources feed one list. Search Console shows what the site was shown for and has no page about; the competitors the client names
rank in the top ten for terms the site has no page about; and the watchlist holds terms somebody chose to track that no page carries.
The detection is the Decision engine's own (`demand_gaps`, `content_gap_signals`): this module only joins the three, prices them for
reading and adds what a person set aside.

Topic gaps are different: whole subjects the site's pages never cover, found by a model from the site's own topics, titles and searches.
That one is asked for on demand (`content_briefs.run_topics`), because it costs a model call.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.decisions.content_gaps import _INTENT, DemandGap, TermGap
from app.models.client import Client
from app.models.schema_tools import ContentState
from app.services import demand_gaps
from app.services.content_gap_signals import scan_term_gaps

LIST_SIZE = 80


def _near(gap: DemandGap | TermGap) -> list[dict[str, Any]]:
    return [{"url": n.url, "title": n.title, "shared": list(n.shared)} for n in gap.nearest]


def _intent(codes: tuple[str, ...]) -> list[str]:
    return [_INTENT.get(c, c) for c in codes]


def _why(gap: DemandGap | TermGap) -> str:
    if gap.absent_words:
        return f"No page on the site uses {', '.join(gap.absent_words)}."
    if not gap.nearest:
        return "No page on the site shares its words."
    share = round(gap.best_overlap * 100)
    return f"The closest page covers {share}% of its words, not enough to be about it."


def _action(gap: DemandGap | TermGap) -> str:
    return "Add to an existing page" if (not gap.absent_words and gap.best_overlap >= 0.5) else "Write a new page"


def ignored(db: Session, client: Client, area: str) -> set[str]:
    return {k for (k,) in db.query(ContentState.key).filter(ContentState.client_id == client.id, ContentState.area == area)}


def build(db: Session, client: Client, *, show_ignored: bool = False, q: str | None = None) -> dict[str, Any]:
    demand = demand_gaps.scan_demand_gaps(db, client)
    tracked = scan_term_gaps(db, client)
    blocked = demand.blocked or tracked.blocked
    if blocked:
        return {"blocked": blocked, "gaps": [], "counts": {}, "notes": [], "ignored_total": 0}

    items: dict[str, dict[str, Any]] = {}

    def add_demand(g: DemandGap) -> None:
        sources = []
        if g.impressions > 0:
            sources.append("searched")
        if g.competitors:
            sources.append("competitor")
        items[g.term] = {
            "term": g.term, "sources": sources or ["searched"], "impressions": round(g.impressions), "clicks": round(g.clicks),
            "position": None if g.position is None else round(g.position, 1), "volume": g.volume, "difficulty": g.difficulty,
            "opportunity": round(g.opportunity), "intents": _intent(g.intents), "priced": g.priced,
            "competitors": [{"domain": d, "position": round(p, 1)} for d, p in g.competitors[:5]],
            "also_covers": [t for t, _ in g.also_covers[:5]], "nearest": _near(g), "why": _why(g), "action": _action(g),
            "page_now": g.stand_in_url,
        }

    for g in demand.gaps:
        add_demand(g)
    # Searches the site is shown for with no page and no volume data yet: still gaps, listed after the ones that can be ranked.
    waiting, _, _ = demand_gaps.demand_candidates(db, client)
    for g in waiting:
        if g.term not in items:
            add_demand(g)
    for t in tracked.gaps:
        held = items.get(t.term)
        if held is not None:
            held["sources"] = sorted({*held["sources"], "watchlist"})
            continue
        items[t.term] = {
            "term": t.term, "sources": ["watchlist"], "impressions": 0, "clicks": 0, "position": None, "volume": t.volume,
            "difficulty": t.difficulty, "opportunity": round(t.opportunity), "intents": _intent(t.intents), "priced": True, "competitors": [],
            "also_covers": [x for x, _ in t.also_covers[:5]], "nearest": _near(t), "why": _why(t), "action": _action(t), "page_now": None,
        }

    set_aside = ignored(db, client, "gap")
    needle = " ".join((q or "").lower().split())
    rows = []
    for item in items.values():
        item["ignored"] = item["term"] in set_aside
        if item["ignored"] != show_ignored:
            continue
        if needle and needle not in item["term"] and not any(needle in n["url"].lower() or needle in (n["title"] or "").lower() for n in item["nearest"]):
            continue
        rows.append(item)
    rows.sort(key=lambda r: (-r["opportunity"], -r["impressions"], r["term"]))

    live = [i for i in items.values() if not i["ignored"]]
    summary = {**demand.summary, **tracked.summary}
    notes = []
    waiting_n = sum(1 for i in live if not i["priced"])
    if waiting_n:
        notes.append(f"{waiting_n} of these have no volume data yet, so they are listed after the ones that can be ranked. Volume is bought monthly for the largest.")
    notes.append("Opportunity is the searches a month a page could compete for: volume, reduced by how hard the term is. It is not a forecast of visits.")
    return {
        "blocked": None, "q": needle or None, "showing_ignored": show_ignored,
        "counts": {
            "gaps": len(live), "searched": sum(1 for i in live if "searched" in i["sources"]), "competitor": sum(1 for i in live if "competitor" in i["sources"]),
            "watchlist": sum(1 for i in live if "watchlist" in i["sources"]), "opportunity": sum(i["opportunity"] for i in live),
            "pages_searched": summary.get("pages_searched") or tracked.summary.get("pages_searched"),
        },
        "ignored_total": len(set_aside), "gaps": rows[:LIST_SIZE], "gaps_total": len(rows), "notes": notes,
    }
