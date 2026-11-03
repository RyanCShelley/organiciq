"""CTR optimizer: where pages and searches get fewer clicks than their position should earn, ranked by the clicks that are available.

A (search, page) pair at an average position of 1 to 20 is held against the industry click-through reference the Decision engine already
uses (`app.decisions.ctr_curve`, the user-selected AI Overviews + Organic curve). It is below benchmark when it earns under half the
clicks the reference expects there and the shortfall is worth fixing. Brand searches are left out: people who type the brand's name
are navigating, and no title change moves them.

The site's clickability score is how many clicks it gets for every 100 the reference expects at those positions, month by month.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions import visibility_candidates as vc
from app.decisions.ctr_curve import MIN_RECOVERABLE_CLICKS, REFERENCE_SCENARIO, UNDERPERFORMANCE_RATIO, expected_ctr_percent
from app.models.annotation import Annotation
from app.models.bing_stats import FactBingQueryStat
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.engine_task import EngineTask
from app.models.gsc import FactGscQueryPage

#: A pair needs this many impressions in the range before its click-through says anything.
MIN_IMPRESSIONS = 100
PAGES_SHOWN = 60
SEARCHES_PER_PAGE = 10
MONTHS_SHOWN = 12
WINDOW_DAYS = 28


def expected_ctr(position: float) -> float:
    return expected_ctr_percent(position, scenario=REFERENCE_SCENARIO)


def _pairs(db: Session, client: Client, start: date, end: date, brand: list[str]) -> dict[tuple[str, str], dict[str, float]]:
    """Each non-brand (search, page) pair at positions 1 to 20: impressions, clicks, and the impression-weighted position."""
    q = func.lower(func.trim(FactGscQueryPage.query))
    rows = (
        db.query(
            q, FactGscQueryPage.normalized_url, func.sum(FactGscQueryPage.impressions), func.sum(FactGscQueryPage.clicks),
            func.sum(FactGscQueryPage.average_position * FactGscQueryPage.impressions),
        )
        .filter(FactGscQueryPage.client_id == client.id, FactGscQueryPage.date >= start, FactGscQueryPage.date <= end)
        .group_by(q, FactGscQueryPage.normalized_url)
        .all()
    )
    out: dict[tuple[str, str], dict[str, float]] = {}
    for query, url, imp, clk, weighted in rows:
        imp = float(imp or 0)
        if imp <= 0 or vc.is_brand(query, brand):
            continue
        position = float(weighted or 0) / imp
        if not 1 <= position <= 20:
            continue
        out[(query, url)] = {"impressions": imp, "clicks": float(clk or 0), "position": position}
    return out


def _grade(pair: dict[str, float]) -> dict[str, Any]:
    exp_ctr = expected_ctr(pair["position"])
    expected = pair["impressions"] * exp_ctr / 100
    short = max(0.0, expected - pair["clicks"])
    below = pair["impressions"] >= MIN_IMPRESSIONS and pair["clicks"] < UNDERPERFORMANCE_RATIO * expected and short >= MIN_RECOVERABLE_CLICKS
    return {
        "ctr": round(pair["clicks"] / pair["impressions"] * 100, 2), "expected_ctr": round(exp_ctr, 2),
        "expected_clicks": round(expected, 1), "extra_clicks": round(short, 1) if below else 0.0, "below": below,
    }


def _score(pairs: dict[Any, dict[str, float]]) -> tuple[int | None, float, float]:
    """Clicks earned per 100 the reference expects, over the pairs with enough impressions. Also the clicks and the expected clicks."""
    clicks = expected = 0.0
    for p in pairs.values():
        if p["impressions"] < MIN_IMPRESSIONS:
            continue
        clicks += p["clicks"]
        expected += p["impressions"] * expected_ctr(p["position"]) / 100
    return (round(100 * clicks / expected) if expected > 0 else None), clicks, expected


def _month_start(day: date) -> date:
    return day.replace(day=1)


def monthly(db: Session, client: Client, end: date, brand: list[str]) -> list[dict[str, Any]]:
    """The clickability score for each of the last twelve months, ending with the month of `end`."""
    first = _month_start(end)
    for _ in range(MONTHS_SHOWN - 1):
        first = _month_start(first - timedelta(days=1))
    out = []
    cursor = first
    while cursor <= end:
        nxt = _month_start(cursor + timedelta(days=32))
        last = min(nxt - timedelta(days=1), end)
        pairs = _pairs(db, client, cursor, last, brand)
        score, clicks, expected = _score(pairs)
        extra = sum(_grade(p)["extra_clicks"] for p in pairs.values())
        out.append({"month": f"{cursor.year:04d}-{cursor.month:02d}", "score": score, "extra_clicks": round(extra), "clicks": round(clicks), "expected_clicks": round(expected)})
        cursor = nxt
    return out


def build(db: Session, client: Client, start: date, end: date) -> dict[str, Any]:
    brand = vc.brand_keys(client)
    pairs = _pairs(db, client, start, end, brand)
    score, clicks, expected = _score(pairs)
    titles = {u: (t, d) for u, t, d in db.query(FactCrawlPageSnapshot.normalized_url, FactCrawlPageSnapshot.title, FactCrawlPageSnapshot.description).filter(
        FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY)}

    by_page: dict[str, list[tuple[str, dict[str, float], dict[str, Any]]]] = defaultdict(list)
    for (query, url), p in pairs.items():
        by_page[url].append((query, p, _grade(p)))

    pages = []
    for url, rows in by_page.items():
        imp = sum(p["impressions"] for _, p, _ in rows)
        if imp < MIN_IMPRESSIONS:
            continue
        clk = sum(p["clicks"] for _, p, _ in rows)
        exp = sum(g["expected_clicks"] for _, _, g in rows)
        extra = sum(g["extra_clicks"] for _, _, g in rows)
        flagged = [(q, p, g) for q, p, g in rows if g["below"]]
        top = max(rows, key=lambda r: r[1]["impressions"])
        pages.append(
            {
                "url": url, "title": titles.get(url, (None, None))[0], "impressions": round(imp), "clicks": round(clk),
                "ctr": round(clk / imp * 100, 2), "expected_clicks": round(exp), "extra_clicks": round(extra, 1),
                "position": round(sum(p["position"] * p["impressions"] for _, p, _ in rows) / imp, 1),
                "searches": len(rows), "searches_below": len(flagged), "top_search": top[0],
                "below": extra > 0,
            }
        )
    pages.sort(key=lambda r: (-r["extra_clicks"], -r["impressions"]))

    searches = []
    for (query, url), p in pairs.items():
        g = _grade(p)
        if g["below"]:
            searches.append({"query": query, "url": url, "impressions": round(p["impressions"]), "clicks": round(p["clicks"]), "position": round(p["position"], 1), **g})
    searches.sort(key=lambda r: -r["extra_clicks"])

    series = monthly(db, client, end, brand)
    first, last, days = db.query(func.min(FactGscQueryPage.date), func.max(FactGscQueryPage.date), func.count(func.distinct(FactGscQueryPage.date))).filter(
        FactGscQueryPage.client_id == client.id, FactGscQueryPage.date >= start, FactGscQueryPage.date <= end).one()
    return {
        "coverage": {"first": first.isoformat() if first else None, "last": last.isoformat() if last else None, "days": int(days or 0)},
        "from": start.isoformat(), "to": end.isoformat(), "benchmark": REFERENCE_SCENARIO,
        "rule": f"A search is below benchmark when it earns under {int(UNDERPERFORMANCE_RATIO * 100)}% of the clicks the reference expects at its position, with at least {MIN_IMPRESSIONS} impressions and {MIN_RECOVERABLE_CLICKS} clicks to gain. Brand searches are left out.",
        "score": score, "clicks": round(clicks), "expected_clicks": round(expected),
        "extra_clicks": round(sum(p["extra_clicks"] for p in pages)), "pages_below": sum(1 for p in pages if p["below"]), "searches_below": len(searches),
        "pages_counted": len(pages), "searches_counted": sum(1 for p in pairs.values() if p["impressions"] >= MIN_IMPRESSIONS),
        "monthly": series, "pages": pages[:PAGES_SHOWN], "searches": searches[:PAGES_SHOWN], "bing": bing_summary(db, client, start, end, brand),
    }


def bing_summary(db: Session, client: Client, start: date, end: date, brand: list[str]) -> dict[str, Any] | None:
    """The same measure for Bing, which reports by search only (no page), weekly. A week counts in the range it starts in."""
    rows = db.query(FactBingQueryStat.query_key, FactBingQueryStat.impressions, FactBingQueryStat.clicks, FactBingQueryStat.avg_impression_position).filter(
        FactBingQueryStat.client_id == client.id, FactBingQueryStat.week_start >= start, FactBingQueryStat.week_start <= end).all()
    if not rows:
        return None
    agg: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for key, imp, clk, pos in rows:
        if vc.is_brand(key, brand) or pos is None or not imp:
            continue
        a = agg[key]
        a[0] += imp
        a[1] += clk
        a[2] += float(pos) * imp
    pairs = {k: {"impressions": a[0], "clicks": a[1], "position": a[2] / a[0]} for k, a in agg.items() if a[0] and 1 <= a[2] / a[0] <= 20}
    score, clicks, expected = _score(pairs)
    return {"score": score, "clicks": round(clicks), "expected_clicks": round(expected), "searches": len(pairs)} if score is not None else None


def page_detail(db: Session, client: Client, url: str, start: date, end: date) -> dict[str, Any]:
    brand = vc.brand_keys(client)
    pairs = {k: v for k, v in _pairs(db, client, start, end, brand).items() if k[1] == url}
    snap = db.query(FactCrawlPageSnapshot).filter(FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot.normalized_url == url).first()
    searches = [{"query": q, "impressions": round(p["impressions"]), "clicks": round(p["clicks"]), "position": round(p["position"], 1), **_grade(p)} for (q, _), p in pairs.items()]
    searches.sort(key=lambda r: (-r["extra_clicks"], -r["impressions"]))
    bing = {}
    if searches:
        keys = [s["query"] for s in searches[:SEARCHES_PER_PAGE]]
        for key, imp, clk, pos in db.query(FactBingQueryStat.query_key, func.sum(FactBingQueryStat.impressions), func.sum(FactBingQueryStat.clicks), func.avg(FactBingQueryStat.avg_impression_position)).filter(
            FactBingQueryStat.client_id == client.id, FactBingQueryStat.query_key.in_(keys), FactBingQueryStat.week_start >= start, FactBingQueryStat.week_start <= end).group_by(FactBingQueryStat.query_key):
            bing[key] = {"impressions": int(imp or 0), "clicks": int(clk or 0), "position": round(float(pos), 1) if pos is not None else None}
    for s in searches:
        s["bing"] = bing.get(s["query"])
    return {
        "url": url, "title": snap.title if snap else None, "description": snap.description if snap else None,
        "title_length": len((snap.title or "")) if snap else None, "description_length": len((snap.description or "")) if snap else None,
        "searches": searches[:SEARCHES_PER_PAGE], "searches_total": len(searches), "changes": changes_for(db, client, url),
    }


def _ctr_between(db: Session, client: Client, url: str, start: date, end: date, brand: list[str]) -> dict[str, Any] | None:
    pairs = {k: v for k, v in _pairs(db, client, start, end, brand).items() if k[1] == url}
    imp = sum(p["impressions"] for p in pairs.values())
    if imp < 30:
        return None
    clk = sum(p["clicks"] for p in pairs.values())
    pos = sum(p["position"] * p["impressions"] for p in pairs.values()) / imp
    return {"impressions": round(imp), "clicks": round(clk), "ctr": round(clk / imp * 100, 2), "position": round(pos, 1)}


def changes_for(db: Session, client: Client, url: str, today: date | None = None) -> list[dict[str, Any]]:
    """Work done on this page (a shipped task, a change-log note), with its click-through in the 28 days before against the 28 days after."""
    today = today or date.today()
    brand = vc.brand_keys(client)
    events: list[tuple[date, str, str]] = []
    for t in db.query(EngineTask).filter(EngineTask.client_id == client.id, EngineTask.page_url == url, EngineTask.status == "shipped", EngineTask.shipped_at.isnot(None)):
        events.append((t.shipped_at.date(), "Shipped", t.title))
    for a in db.query(Annotation).filter(Annotation.client_id == client.id, Annotation.page_url == url, Annotation.engine_uid.is_(None)):
        events.append((a.date, "Noted", a.description))
    out = []
    for day, kind, text in sorted(events, reverse=True)[:6]:
        before = _ctr_between(db, client, url, day - timedelta(days=WINDOW_DAYS), day - timedelta(days=1), brand)
        ready = day + timedelta(days=WINDOW_DAYS) <= today
        after = _ctr_between(db, client, url, day + timedelta(days=1), day + timedelta(days=WINDOW_DAYS), brand) if ready else None
        out.append({"date": day.isoformat(), "kind": kind, "text": text, "before": before, "after": after, "measured_on": (day + timedelta(days=WINDOW_DAYS)).isoformat() if not ready else None})
    return out
