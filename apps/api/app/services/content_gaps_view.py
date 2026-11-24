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

from app.decisions.content_gaps import _INTENT, DemandGap, TermGap, content_words
from app.models.client import Client
from app.models.schema_tools import ContentState
from app.services import demand_gaps
from app.services.content_gap_signals import scan_term_gaps
from app.services.review_visibility import key_of

LIST_SIZE = 80
WAITING_MIN_IMPRESSIONS = 200
WAITING_MAX_POSITION = 50.0
WAITING_LIMIT = 20


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
    keys = {k for (k,) in db.query(ContentState.key).filter(ContentState.client_id == client.id, ContentState.area == area)}
    if area == "gap":
        return {key_of(k) for k in keys if key_of(k)}
    return keys


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

    # Unpriced Search Console candidates awaiting volume data, guarded against noise and duplicates.
    covered_by_priced = (
        set(items)
        | {alt for g in demand.gaps for alt, _ in g.also_covers}
        | {alt for t in tracked.gaps for alt, _ in t.also_covers}
    )
    priced_word_sets = [w for term in covered_by_priced if (w := content_words(term))]
    waiting = []
    for g in demand.unpriced:
        if g.term in covered_by_priced:
            continue
        words = content_words(g.term)
        if not words or any(words <= pw or pw <= words for pw in priced_word_sets):
            continue
        if g.impressions < WAITING_MIN_IMPRESSIONS:
            continue
        if g.position is not None and g.position > WAITING_MAX_POSITION:
            continue
        if len(words) < 2 and g.clicks < 2:
            continue
        waiting.append(g)
    waiting.sort(key=lambda g: (-g.impressions, -g.clicks, g.term))
    for g in waiting[:WAITING_LIMIT]:
        add_demand(g)

    set_aside = ignored(db, client, "gap")
    needle = " ".join((q or "").lower().split())
    rows = []
    for item in items.values():
        item["ignored"] = key_of(item["term"]) in set_aside
        if item["ignored"] != show_ignored:
            continue
        if needle and needle not in item["term"] and not any(needle in n["url"].lower() or needle in (n["title"] or "").lower() for n in item["nearest"]):
            continue
        rows.append(item)
    rows.sort(key=lambda r: (-r["opportunity"], -r["impressions"], r["term"]))

    live = [i for i in items.values() if not i["ignored"]]
    ignored_items = [i for i in items.values() if i["ignored"]]
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
        "ignored_total": len(ignored_items), "gaps": rows[:LIST_SIZE], "gaps_total": len(rows), "notes": notes,
    }
