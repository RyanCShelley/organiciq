"""Traffic candidates: where organic sessions fell, judged against the site's own trend.

From the plan, which tested these on 50 live GA4 properties over 24 months:

- A site's pages are judged against *that site's* year-over-year change, not against zero: the median
  site was down 18% to 31% year over year, so "down" alone says almost nothing.
- Few pages have the volume for a page-level test (the median site has one page over 100 organic
  sessions), so everything is also tested rolled up to each watchlist bucket and to the whole site.
- **Sudden**: the latest month is down 30% or more on a prior month of 100+ sessions.
- **Slow bleed**: the last three months keep at most half the share of last year's that the whole site
  kept, on a baseline (the same three months a year earlier) of 150+ sessions.

A unit that fails the tests but is still falling stays on the list as *possible*, with the reason;
the filters rank and label, they never hide. The list is filled to 20 with whatever is falling most.
The thresholds are constants here, shown on the screen, and still to be approved.

Organic search sessions only: the work this engine plans is organic work.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.visibility_candidates import _aggregate, add_months
from app.models.client import Client
from app.models.config import OrganicChannel
from app.models.ga4 import FactGa4Traffic
from app.models.watchlist import WatchlistBucket, WatchlistKeyword

LIST_SIZE = 20
SUDDEN_MIN_PRIOR = 100.0
SUDDEN_DROP = 0.30
SLOW_MIN_BASELINE = 150.0
#: A unit's year-over-year retention must be no more than this fraction of the whole site's.
SLOW_RELATIVE_RETENTION = 0.5
#: The softer tests that keep a falling unit on the list as "possible".
POSSIBLE_MIN_PRIOR = 30.0
POSSIBLE_DROP = 0.20
POSSIBLE_MIN_BASELINE = 50.0
POSSIBLE_RELATIVE_RETENTION = 0.75
#: A page needs this many organic sessions in the three months (now or a year ago) to be listed as a page.
PAGE_MIN_SESSIONS = 30.0
#: Pages that a bucket's searches reach: impressions over the three months for a search containing a term.
BUCKET_PAGE_MIN_IMPRESSIONS = 5.0

ORGANIC = OrganicChannel.ORGANIC_SEARCH


def is_real_page(url: str) -> bool:
    """GA4 reports sessions it could not place as "(not set)". That is not a page anyone can fix."""
    return url.startswith(("http://", "https://"))


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _months_back(month_start: date, n: int) -> list[str]:
    return [_month_key(add_months(month_start, -i)) for i in range(n)]


def _pct(current: float | None, previous: float | None) -> float | None:
    if current is None or not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def monthly_sessions(db: Session, client_id: UUID, first: date, last: date) -> dict[str, dict[str, float]]:
    """`{page_url: {YYYY-MM: organic sessions}}` over the window."""
    month = func.date_trunc("month", FactGa4Traffic.date)
    rows = (
        db.query(FactGa4Traffic.normalized_url, month, func.sum(FactGa4Traffic.sessions))
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.channel == ORGANIC,
            FactGa4Traffic.date >= first,
            FactGa4Traffic.date <= last,
        )
        .group_by(FactGa4Traffic.normalized_url, month)
        .all()
    )
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for url, m, total in rows:
        if not is_real_page(url):
            continue
        out[url][_month_key(m.date() if hasattr(m, "date") else m)] = float(total or 0)
    return out


def bucket_pages(db: Session, client: Client, month_start: date, terms: list[str]) -> set[str]:
    """Pages that Search Console shows for a search containing one of the bucket's terms."""
    start = add_months(month_start, -2)
    end = add_months(month_start, 1).replace(day=1)
    from datetime import timedelta

    rows = _aggregate(db, client.id, start, end - timedelta(days=1), terms)
    return {url for (_, url), n in rows.items() if n["impressions"] >= BUCKET_PAGE_MIN_IMPRESSIONS}


def _sum(series: dict[str, float], months: list[str]) -> float:
    return sum(series.get(m, 0.0) for m in months)


def _measure(series: dict[str, float], cur: str, prev: str, cur3: list[str], ly3: list[str]) -> dict[str, float]:
    return {
        "current": series.get(cur, 0.0),
        "previous": series.get(prev, 0.0),
        "cur3": _sum(series, cur3),
        "ly3": _sum(series, ly3),
    }


def judge(unit: dict[str, float], site_ratio: float | None) -> dict[str, Any]:
    """Which tests a unit passes. `site_ratio` is the whole site's retention (this year over last), or None."""
    cur, prev, cur3, ly3 = unit["current"], unit["previous"], unit["cur3"], unit["ly3"]
    drop = (prev - cur) / prev if prev else 0.0
    sudden = prev >= SUDDEN_MIN_PRIOR and drop >= SUDDEN_DROP
    soft_sudden = prev >= POSSIBLE_MIN_PRIOR and drop >= POSSIBLE_DROP

    retention = cur3 / ly3 if ly3 else None
    slow = soft_slow = False
    if site_ratio is not None and retention is not None:
        slow = ly3 >= SLOW_MIN_BASELINE and retention <= SLOW_RELATIVE_RETENTION * site_ratio
        soft_slow = ly3 >= POSSIBLE_MIN_BASELINE and retention <= POSSIBLE_RELATIVE_RETENTION * site_ratio

    expected_monthly = ly3 * site_ratio / 3 if site_ratio is not None else None
    shortfall = max(0.0, expected_monthly - cur3 / 3) if expected_monthly is not None else 0.0
    at_stake = max(max(prev - cur, 0.0) if (sudden or soft_sudden) else 0.0, shortfall if (slow or soft_slow) else 0.0)
    return {
        "sudden": sudden,
        "slow_bleed": slow,
        "possible": (soft_sudden or soft_slow) and not (sudden or slow),
        "soft_sudden": soft_sudden,
        "soft_slow": soft_slow,
        "retention": retention,
        "at_stake": round(at_stake, 1),
        "drop": drop,
    }


def _flag(j: dict[str, Any]) -> str | None:
    if j["sudden"] and j["slow_bleed"]:
        return "both"
    return "sudden" if j["sudden"] else "slow_bleed" if j["slow_bleed"] else None


def _reason(j: dict[str, Any], unit: dict[str, float]) -> str | None:
    """Why a unit that is falling is only *possible*: which test it missed."""
    if j["sudden"] or j["slow_bleed"]:
        return None
    if not j["possible"]:
        if unit["previous"] > unit["current"] and j["drop"] >= POSSIBLE_DROP:
            return f"too small to judge: {round(unit['previous'])} sessions the month before, {round(unit['current'])} last month"
        return "no decline flagged: one of the busiest"
    parts = []
    if j["soft_sudden"]:
        if unit["previous"] < SUDDEN_MIN_PRIOR:
            parts.append(f"only {round(unit['previous'])} sessions the month before, under the {int(SUDDEN_MIN_PRIOR)} the sudden test needs")
        else:
            parts.append(f"down {round(j['drop'] * 100)}%, under the {int(SUDDEN_DROP * 100)}% the sudden test needs")
    if j["soft_slow"]:
        if unit["ly3"] < SLOW_MIN_BASELINE:
            parts.append(f"only {round(unit['ly3'])} sessions in the same three months last year, under the {int(SLOW_MIN_BASELINE)} the slow-bleed test needs")
        else:
            parts.append("losing share against the site, but not by enough to pass the slow-bleed test")
    return "; ".join(parts) or "falling, but not by enough to pass a test"


def build(db: Session, client: Client, month: str, bucket_id: UUID | None = None) -> dict[str, Any]:
    """Traffic candidates as of `month` (YYYY-MM, a complete month)."""
    year, mon = int(month[:4]), int(month[5:7])
    month_start = date(year, mon, 1)
    cur, prev = _month_key(month_start), _month_key(add_months(month_start, -1))
    cur3 = _months_back(month_start, 3)
    ly3 = [_month_key(add_months(month_start, -(i + 12))) for i in range(3)]

    window_first = add_months(month_start, -14)
    window_last = add_months(month_start, 1).replace(day=1)
    from datetime import timedelta

    pages = monthly_sessions(db, client.id, window_first, window_last - timedelta(days=1))

    site_series: dict[str, float] = defaultdict(float)
    for series in pages.values():
        for m, v in series.items():
            site_series[m] += v
    site = _measure(site_series, cur, prev, cur3, ly3)
    has_yoy = site["ly3"] > 0
    site_ratio = (site["cur3"] / site["ly3"]) if has_yoy else None

    buckets = (
        db.query(WatchlistBucket)
        .filter(WatchlistBucket.client_id == client.id)
        .order_by(WatchlistBucket.sort_order, WatchlistBucket.name)
        .all()
    )
    chosen = None
    if bucket_id is not None:
        chosen = next((b for b in buckets if b.id == bucket_id), None)
        if chosen is None:
            raise LookupError("That bucket is not on this client's watchlist.")

    units: list[dict[str, Any]] = []

    def add(level: str, key: str, label: str, series: dict[str, float], bucket: str | None = None) -> None:
        m = _measure(series, cur, prev, cur3, ly3)
        j = judge(m, site_ratio)
        units.append(
            {
                "level": level,
                "key": key,
                "label": label,
                "bucket": bucket,
                "sessions": {"current": round(m["current"]), "previous": round(m["previous"]), "change_pct": _pct(m["current"], m["previous"])},
                "three_months": {"current": round(m["cur3"]), "last_year": round(m["ly3"]), "change_pct": _pct(m["cur3"], m["ly3"])},
                "flag": _flag(j),
                "strength": "strong" if (j["sudden"] or j["slow_bleed"]) else "possible",
                "reason": _reason(j, m),
                "at_stake": j["at_stake"],
                "_falling": j["sudden"] or j["slow_bleed"] or j["possible"],
                "_size": m["cur3"] + m["ly3"],
            }
        )

    scope_pages: set[str] | None = None
    scope_label = "the whole site"
    if chosen is not None:
        terms = sorted({" ".join(k.keyword.lower().split()) for k in db.query(WatchlistKeyword).filter(WatchlistKeyword.bucket_id == chosen.id)})
        scope_pages = bucket_pages(db, client, month_start, terms)
        scope_label = chosen.name

    if scope_pages is None:
        add("site", "site", "The whole site", site_series)
    for b in buckets:
        if chosen is not None and b.id != chosen.id:
            continue
        terms = sorted({" ".join(k.keyword.lower().split()) for k in db.query(WatchlistKeyword).filter(WatchlistKeyword.bucket_id == b.id)})
        urls = scope_pages if (chosen is not None and b.id == chosen.id) else bucket_pages(db, client, month_start, terms)
        roll: dict[str, float] = defaultdict(float)
        for url in urls:
            for m, v in pages.get(url, {}).items():
                roll[m] += v
        add("bucket", str(b.id), b.name, roll)

    for url, series in pages.items():
        if scope_pages is not None and url not in scope_pages:
            continue
        m = _measure(series, cur, prev, cur3, ly3)
        if max(m["cur3"], m["ly3"]) < PAGE_MIN_SESSIONS:
            continue
        add("page", url, url, series)

    falling = sorted((u for u in units if u["_falling"]), key=lambda u: (u["strength"] != "strong", -u["at_stake"], -u["_size"]))
    rest = sorted((u for u in units if not u["_falling"] and u["level"] == "page"), key=lambda u: -u["_size"])
    listed = (falling + rest)[:LIST_SIZE]
    for u in units:
        u.pop("_falling", None)
        u.pop("_size", None)

    return {
        "month": month,
        "scope": scope_label,
        "bucket": None if chosen is None else {"id": str(chosen.id), "name": chosen.name},
        "windows": {"current": cur, "previous": prev, "three_months": [cur3[-1], cur3[0]], "last_year": [ly3[-1], ly3[0]]},
        "site": {
            "sessions": {"current": round(site["current"]), "previous": round(site["previous"]), "change_pct": _pct(site["current"], site["previous"])},
            "three_months": {"current": round(site["cur3"]), "last_year": round(site["ly3"]), "change_pct": _pct(site["cur3"], site["ly3"])},
            "has_last_year": has_yoy,
        },
        "counts": {
            "strong": sum(1 for u in units if u["strength"] == "strong" and u["flag"]),
            "possible": sum(1 for u in units if u["strength"] == "possible" and u["flag"] is None and u["reason"] and "no decline" not in u["reason"]),
            "listed": len(listed),
        },
        "candidates": listed,
        "thresholds": {
            "sudden": f"down {int(SUDDEN_DROP * 100)}% or more on a prior month of {int(SUDDEN_MIN_PRIOR)}+ sessions",
            "slow_bleed": f"last 3 months keep at most {int(SLOW_RELATIVE_RETENTION * 100)}% of the share the whole site kept of last year's, on a baseline of {int(SLOW_MIN_BASELINE)}+ sessions",
        },
        "notes": [
            "Organic search sessions, by landing page. A page is judged against the whole site's own year-over-year change, not against zero.",
            "A bucket's pages are the pages Search Console shows for a search containing one of its terms. Most pages are too small for a page-level test, so each bucket and the whole site are tested too.",
            ("Last year's months are missing from the data, so the slow-bleed test cannot run." if not has_yoy else "Slow bleed compares the last three months with the same three months a year earlier."),
            "A unit that is falling but fails the tests stays on the list as possible, with the reason.",
        ],
    }


def queries_lost(db: Session, client: Client, month: str, page: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """The searches that lost the most clicks (then impressions) on a page, three months against the three before."""
    from app.decisions.visibility_candidates import windows
    from app.models.gsc import FactGscQueryPage

    year, mon = int(month[:4]), int(month[5:7])
    span = windows(date(year, mon, 1))
    q = func.lower(func.trim(FactGscQueryPage.query))

    def read(window: tuple[date, date]) -> dict[str, dict[str, float]]:
        rows = (
            db.query(
                q,
                func.sum(FactGscQueryPage.impressions),
                func.sum(FactGscQueryPage.clicks),
                func.sum(FactGscQueryPage.average_position * FactGscQueryPage.impressions),
            )
            .filter(
                FactGscQueryPage.client_id == client.id,
                FactGscQueryPage.normalized_url == page,
                FactGscQueryPage.date >= window[0],
                FactGscQueryPage.date <= window[1],
            )
            .group_by(q)
            .all()
        )
        out = {}
        for text, imp, clk, weighted in rows:
            imp = float(imp or 0)
            if imp > 0:
                out[text] = {"impressions": imp, "clicks": float(clk or 0), "position": float(weighted or 0) / imp}
        return out

    now, before = read(span["current"]), read(span["previous"])
    lost = []
    for text, b in before.items():
        if b["impressions"] < 20:
            continue
        n = now.get(text, {"impressions": 0.0, "clicks": 0.0, "position": None})
        lost.append(
            {
                "query": text,
                "clicks": {"current": round(n["clicks"]), "previous": round(b["clicks"])},
                "impressions": {"current": round(n["impressions"]), "previous": round(b["impressions"])},
                "position": {"current": None if n["position"] is None else round(n["position"], 1), "previous": round(b["position"], 1)},
                "clicks_lost": round(b["clicks"] - n["clicks"]),
                "impressions_lost": round(b["impressions"] - n["impressions"]),
            }
        )
    lost = [x for x in lost if x["clicks_lost"] > 0 or x["impressions_lost"] > 0]
    lost.sort(key=lambda x: (-x["clicks_lost"], -x["impressions_lost"]))
    return lost[:limit]
