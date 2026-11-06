"""What Search Console and Bing say about each page, and how close each page is to what the site is going after.

Content refreshes judges a page on three sources over the same three months against the same three a year earlier: Google Analytics sessions
(`traffic_candidates`), Search Console clicks and impressions (here), and Bing clicks. Bing reports by search, not by page, so each Bing search is
counted for the page Search Console shows for that search.

Relevance is by meaning as well as by words: the page's title and headings (the vectors the inlink suggester uses) are held against the watchlist's
terms, so a page about a topic the site is going after still counts when its title does not contain the exact term.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.decisions.visibility_candidates import add_months
from app.models.bing_stats import FactBingQueryStat
from app.models.client import Client
from app.models.gsc import FactGscPage, FactGscQueryPage

logger = logging.getLogger("organiciq.refresh_signals")

#: A page needs this many Search Console clicks in the three months (now or a year ago) to be judged on them.
GSC_PAGE_MIN_CLICKS = 15.0
#: Below this many, the whole site's Search Console clicks say nothing about a trend.
GSC_SITE_MIN_CLICKS = 30.0
#: A page is "related" to a target topic when its meaning is at least this close to one of the watchlist's terms (cosine, 0 to 1). Not tuned on live data.
RELATED_MIN_SIMILARITY = 0.35
#: Search Console clicks this steady (against the whole site) while Analytics fell mean the fall may be in the tracking.
STEADY_RETENTION = 0.9


def windows(month_start: date) -> tuple[tuple[date, date], tuple[date, date]]:
    """The three months ending with `month_start`'s month, and the same three a year earlier, as (first day, last day)."""
    def span(end_month: date) -> tuple[date, date]:
        return add_months(end_month, -2), add_months(end_month, 1) - timedelta(days=1)

    return span(month_start), span(add_months(month_start, -12))


def search_console(db: Session, client: Client, cur: tuple[date, date], ly: tuple[date, date]) -> dict[str, dict[str, float]]:
    """Per page: clicks and impressions in the three months and the three a year earlier."""
    def within(column: Any, window: tuple[date, date]) -> Any:
        return func.sum(case((FactGscPage.date.between(*window), column), else_=0))

    rows = (
        db.query(FactGscPage.normalized_url, within(FactGscPage.clicks, cur), within(FactGscPage.clicks, ly), within(FactGscPage.impressions, cur), within(FactGscPage.impressions, ly))
        .filter(FactGscPage.client_id == client.id, FactGscPage.date >= ly[0], FactGscPage.date <= cur[1])
        .group_by(FactGscPage.normalized_url)
        .all()
    )
    return {url: {"clicks": float(a or 0), "clicks_ly": float(b or 0), "impressions": float(c or 0), "impressions_ly": float(d or 0)} for url, a, b, c, d in rows}


def page_for_search(db: Session, client: Client, cur: tuple[date, date]) -> dict[str, str]:
    """For each search, the page Search Console shows for it the most (by impressions) in the three months."""
    q = func.lower(func.trim(FactGscQueryPage.query))
    rows = (
        db.query(q, FactGscQueryPage.normalized_url, func.sum(FactGscQueryPage.impressions))
        .filter(FactGscQueryPage.client_id == client.id, FactGscQueryPage.date >= cur[0], FactGscQueryPage.date <= cur[1])
        .group_by(q, FactGscQueryPage.normalized_url)
        .all()
    )
    best: dict[str, tuple[float, str]] = {}
    for query, url, impressions in rows:
        held = best.get(query)
        if held is None or float(impressions or 0) > held[0]:
            best[query] = (float(impressions or 0), url)
    return {query: url for query, (_, url) in best.items()}


def bing(db: Session, client: Client, cur: tuple[date, date], ly: tuple[date, date], owner: dict[str, str]) -> tuple[dict[str, dict[str, float]], bool]:
    """Per page: Bing clicks and impressions, each Bing search counted for the page Search Console shows for it. A week counts in the range it starts in.

    The second value says whether Bing has any numbers for the client at all, so a quiet page is told from a client with no Bing data.
    """
    def within(column: Any, window: tuple[date, date]) -> Any:
        return func.sum(case((FactBingQueryStat.week_start.between(*window), column), else_=0))

    rows = (
        db.query(FactBingQueryStat.query_key, within(FactBingQueryStat.clicks, cur), within(FactBingQueryStat.clicks, ly), within(FactBingQueryStat.impressions, cur), within(FactBingQueryStat.impressions, ly))
        .filter(FactBingQueryStat.client_id == client.id, FactBingQueryStat.week_start >= ly[0], FactBingQueryStat.week_start <= cur[1])
        .group_by(FactBingQueryStat.query_key)
        .all()
    )
    out: dict[str, dict[str, float]] = defaultdict(lambda: {"clicks": 0.0, "clicks_ly": 0.0, "impressions": 0.0, "impressions_ly": 0.0})
    for key, a, b, c, d in rows:
        url = owner.get(" ".join((key or "").lower().split()))
        if url is None:
            continue
        page = out[url]
        page["clicks"] += float(a or 0)
        page["clicks_ly"] += float(b or 0)
        page["impressions"] += float(c or 0)
        page["impressions_ly"] += float(d or 0)
    return dict(out), bool(rows)


def similarity(db: Session, client: Client, snaps: dict[str, Any], terms: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """How close each page's meaning is to its nearest watchlist term: {url: {"term", "topic", "similarity"}}.

    Pages without a crawled snapshot are left out, and so is everything if the text model cannot be loaded: the screen then has the
    exact matches alone, which is what it had before.
    """
    urls = [u for u, s in snaps.items() if s is not None]
    if not urls or not terms:
        return {}
    try:
        from app.services import inlinks, keyword_matcher

        vectors = inlinks._vectors(db, client, [snaps[u] for u in urls])
        matrix = keyword_matcher._embed([t["term"] for t in terms])
        out: dict[str, dict[str, Any]] = {}
        for url in urls:
            scores = matrix @ vectors[url]
            i = int(scores.argmax())
            out[url] = {"term": terms[i]["term"], "topic": terms[i].get("topic"), "similarity": round(float(scores[i]), 2)}
        return out
    except Exception:  # noqa: BLE001 — relatedness is an aid; the list stands without it
        logger.warning("Could not work out how related pages are to the watchlist", exc_info=True)
        return {}


def window_change(now: float, before: float) -> int | None:
    return round((now / before - 1) * 100) if before > 0 else None


def lost_a_month(now: float, before: float, site_ratio: float | None) -> float:
    """Clicks a month the page has lost against what the whole site's own trend says it should have."""
    if site_ratio is None:
        return 0.0
    return max(0.0, (before * site_ratio - now) / 3)


def tracking_gap(sessions_fell: bool, clicks_now: float, clicks_before: float, site_ratio: float | None) -> bool:
    """Analytics says the page lost traffic while Search Console clicks held up with the site: the visits may be going unrecorded."""
    if not sessions_fell or site_ratio is None or clicks_before < GSC_PAGE_MIN_CLICKS * 2:
        return False
    return clicks_now / clicks_before >= STEADY_RETENTION * site_ratio
