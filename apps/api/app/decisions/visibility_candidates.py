"""Visibility candidates: searches where a page is close enough to a better position to be worth moving.

For a bucket on the watchlist (or the whole site), the engine lists up to 20 (search, page)
pairs, ranked by the extra clicks a move would be expected to bring. The filters rank and
label; they never hide. A pair that fails the strength test stays on the list as *possible*,
with the reason.

Bands, from the plan:
  rank 2 or 3     could reach 1
  rank 4 to 10    could reach the top 3
  rank 11 to 20   could reach page one (the upper half, position 5)

Expected extra clicks = impressions x (target CTR - current CTR) / 100, using the tool's
organic CTR benchmark. That benchmark is not monotone past position 7 (positions 11 to 14
read higher than 8 to 10), which would score "reach page one" as no gain at all, so it is
smoothed to never rise with position before use. The target positions are constants below,
shown on every row, so the assumption is visible and one line to change.

Impressions are summed over three complete months and compared with the three before.
Search Console's impression counts changed with Google's reporting change, so change in
impressions is only meaningful inside the period after it; position and clicks are steadier.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.decisions.ctr_curve import expected_ctr_percent
from app.models.client import Client
from app.models.gsc import FactGscDaily, FactGscQueryPage
from app.models.watchlist import WatchlistBucket, WatchlistKeyword

WINDOW_MONTHS = 3
LIST_SIZE = 20
#: Impressions over the window below which a pair is *possible*, not *strong*.
STRONG_MIN_IMPRESSIONS = 100


@dataclass(frozen=True)
class Band:
    key: str
    label: str
    low: int
    high: int
    target_position: int


BANDS = (
    Band("2-3", "Could reach 1", 2, 3, 1),
    Band("4-10", "Could reach the top 3", 4, 10, 3),
    Band("11-20", "Could reach page one", 11, 20, 5),
)


@lru_cache(maxsize=1)
def _smoothed() -> dict[int, float]:
    """The benchmark made non-increasing: a worse position never earns a higher CTR."""
    out: dict[int, float] = {}
    lowest = float("inf")
    for position in range(1, 21):
        lowest = min(lowest, expected_ctr_percent(float(position)))
        out[position] = lowest
    return out


def smoothed_ctr(position: float) -> float:
    curve = _smoothed()
    if position <= 1:
        return curve[1]
    if position >= 20:
        return curve[20]
    lower = int(position)
    return curve[lower] + (curve[lower + 1] - curve[lower]) * (position - lower)


def band_for(position: float) -> Band | None:
    rank = round(position)
    return next((b for b in BANDS if b.low <= rank <= b.high), None)


def expected_extra_clicks(impressions: float, position: float, band: Band) -> float:
    gain = smoothed_ctr(float(band.target_position)) - smoothed_ctr(position)
    return round(max(0.0, impressions * gain / 100), 1)


# ── windows ──────────────────────────────────────────────────────────────────


def add_months(day: date, months: int) -> date:
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    return date(year, month + 1, 1)


def windows(last_month_start: date) -> dict[str, tuple[date, date]]:
    """Three complete months ending with the month that starts on `last_month_start`."""
    start = add_months(last_month_start, -(WINDOW_MONTHS - 1))
    end = add_months(last_month_start, 1) - timedelta(days=1)
    return {
        "current": (start, end),
        "previous": (add_months(start, -WINDOW_MONTHS), start - timedelta(days=1)),
        "last_year": (add_months(start, -12), add_months(end + timedelta(days=1), -12) - timedelta(days=1)),
    }


# ── data ─────────────────────────────────────────────────────────────────────


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _contains(query: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", query) is not None


def _aggregate(
    db: Session, client_id: UUID, start: date, end: date, terms: list[str] | None
) -> dict[tuple[str, str], dict[str, float]]:
    q = func.lower(func.trim(FactGscQueryPage.query))
    query = db.query(
        q.label("q"),
        FactGscQueryPage.normalized_url,
        func.sum(FactGscQueryPage.impressions),
        func.sum(FactGscQueryPage.clicks),
        func.sum(FactGscQueryPage.average_position * FactGscQueryPage.impressions),
    ).filter(
        FactGscQueryPage.client_id == client_id,
        FactGscQueryPage.date >= start,
        FactGscQueryPage.date <= end,
    )
    if terms:
        query = query.filter(or_(*[q.like(_like(t), escape="\\") for t in terms]))
    out: dict[tuple[str, str], dict[str, float]] = {}
    for text, url, impressions, clicks, weighted in query.group_by("q", FactGscQueryPage.normalized_url).all():
        impressions = float(impressions or 0)
        if impressions <= 0:
            continue
        if terms and not any(_contains(text, t) for t in terms):
            continue
        out[(text, url)] = {
            "impressions": impressions,
            "clicks": float(clicks or 0),
            "position": float(weighted or 0) / impressions,
        }
    return out


def _site_totals(db: Session, client_id: UUID, start: date, end: date) -> dict[str, float]:
    row = (
        db.query(func.sum(FactGscDaily.impressions), func.sum(FactGscDaily.clicks), func.count(func.distinct(FactGscDaily.date)))
        .filter(FactGscDaily.client_id == client_id, FactGscDaily.date >= start, FactGscDaily.date <= end)
        .one()
    )
    return {"impressions": float(row[0] or 0), "clicks": float(row[1] or 0), "days": int(row[2] or 0)}


def _only(n: int) -> str:
    return f"only {n} impression{'' if n == 1 else 's'} in {WINDOW_MONTHS} months"


def _pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current - previous) / previous * 100, 1)


def _best_page_per_search(rows: dict[tuple[str, str], dict[str, float]]) -> dict[str, dict]:
    """One row per search: the page that gets the most impressions for it, and how many pages share it."""
    by_search: dict[str, list[tuple[str, dict[str, float]]]] = defaultdict(list)
    for (text, url), numbers in rows.items():
        by_search[text].append((url, numbers))
    best: dict[str, dict] = {}
    for text, pages in by_search.items():
        url, numbers = max(pages, key=lambda p: p[1]["impressions"])
        best[text] = {"url": url, "pages": len(pages), **numbers}
    return best


# ── the list ─────────────────────────────────────────────────────────────────


def build(db: Session, client: Client, month: str, bucket_id: UUID | None = None) -> dict[str, Any]:
    """Candidates for the three months ending with `month` (YYYY-MM), within a bucket if one is given."""
    year, mon = int(month[:4]), int(month[5:7])
    span = windows(date(year, mon, 1))

    bucket = None
    terms: list[str] | None = None
    watch_terms: list[WatchlistKeyword] = []
    if bucket_id is not None:
        bucket = (
            db.query(WatchlistBucket)
            .filter(WatchlistBucket.id == bucket_id, WatchlistBucket.client_id == client.id)
            .one_or_none()
        )
        if bucket is None:
            raise LookupError("That bucket is not on this client's watchlist.")
        watch_terms = db.query(WatchlistKeyword).filter(WatchlistKeyword.bucket_id == bucket.id).all()
        terms = sorted({" ".join(k.keyword.lower().split()) for k in watch_terms})

    now = _best_page_per_search(_aggregate(db, client.id, *span["current"], terms))
    before = _best_page_per_search(_aggregate(db, client.id, *span["previous"], terms))
    year_ago = _best_page_per_search(_aggregate(db, client.id, *span["last_year"], terms))

    candidates: list[dict[str, Any]] = []
    for text, row in now.items():
        band = band_for(row["position"])
        if band is None:
            continue
        gain = expected_extra_clicks(row["impressions"], row["position"], band)
        strong = row["impressions"] >= STRONG_MIN_IMPRESSIONS
        prior, last_year = before.get(text), year_ago.get(text)
        candidates.append(
            {
                "search": text,
                "page": row["url"],
                "pages_for_search": row["pages"],
                "impressions": round(row["impressions"]),
                "clicks": round(row["clicks"]),
                "position": round(row["position"], 1),
                "band": band.key,
                "band_label": band.label,
                "target_position": band.target_position,
                "expected_extra_clicks": gain,
                "strength": "strong" if strong else "possible",
                "reason": None if strong else _only(round(row["impressions"])),
                "previous": None if prior is None else {"impressions": round(prior["impressions"]), "position": round(prior["position"], 1)},
                "impressions_change_pct": _pct(row["impressions"], prior["impressions"] if prior else None),
                "position_change": None if prior is None else round(prior["position"] - row["position"], 1),
                "last_year": None if last_year is None else {"impressions": round(last_year["impressions"]), "position": round(last_year["position"], 1)},
            }
        )

    candidates.sort(key=lambda c: (c["strength"] != "strong", -c["expected_extra_clicks"], -c["impressions"]))
    listed = candidates[:LIST_SIZE]

    unranked = []
    for keyword in sorted(watch_terms, key=lambda k: -(k.volume or 0)):
        key = " ".join(keyword.keyword.lower().split())
        if not any(_contains(text, key) for text in now) and (keyword.volume or 0) > 0:
            unranked.append(
                {
                    "keyword": keyword.keyword,
                    "volume": keyword.volume,
                    "strength": "possible",
                    "note": "No Google impressions for this term or any search containing it. No competitor was checked.",
                }
            )

    site = {name: _site_totals(db, client.id, *span[name]) for name in ("current", "previous")}
    last_year_days = _site_totals(db, client.id, *span["last_year"])["days"]

    return {
        "month": month,
        "window": {
            "from": span["current"][0].isoformat(),
            "to": span["current"][1].isoformat(),
            "previous_from": span["previous"][0].isoformat(),
            "previous_to": span["previous"][1].isoformat(),
            "months": WINDOW_MONTHS,
            "has_last_year": last_year_days > 0,
        },
        "bucket": None if bucket is None else {"id": str(bucket.id), "name": bucket.name, "terms": terms},
        "site_trend": {
            "impressions_change_pct": _pct(site["current"]["impressions"], site["previous"]["impressions"]),
            "clicks_change_pct": _pct(site["current"]["clicks"], site["previous"]["clicks"]),
        },
        "bands": [
            {"key": b.key, "label": b.label, "target_position": b.target_position,
             "count": sum(1 for c in candidates if c["band"] == b.key)}
            for b in BANDS
        ],
        "counts": {
            "strong": sum(1 for c in candidates if c["strength"] == "strong"),
            "possible": sum(1 for c in candidates if c["strength"] == "possible"),
            "listed": len(listed),
            "found": len(candidates),
        },
        "candidates": listed,
        "unranked": unranked,
        "notes": [
            f"A search counts when its average position over {WINDOW_MONTHS} months is between 2 and 20. A pair with "
            f"under {STRONG_MIN_IMPRESSIONS} impressions is possible, not strong, and stays on the list.",
            "Expected extra clicks = impressions x (CTR at the target position - CTR now), from the organic CTR benchmark "
            "smoothed so a worse position never earns a higher CTR.",
            "Impression counts changed with Google's reporting change, so compare change in impressions only within "
            "the period after it; position and clicks are steadier.",
            "When a bucket is chosen, a search belongs to it if it contains one of the bucket's watchlist terms.",
        ],
    }


#: A bucket is thin when nothing in it is strong and fewer than this many searches are in reach.
THIN_BELOW = 5
#: ...and good when this many are strong.
GOOD_AT = 3
#: Search Console days (of the window) below which no list can be trusted.
MIN_COVERAGE_SHARE = 0.5


def reach_label(strong: int, found: int) -> str:
    if strong == 0 and found < THIN_BELOW:
        return "thin"
    return "good" if strong >= GOOD_AT else "some"


def advise(
    buckets: list[dict[str, Any]],
    focus_bucket_id: str | None,
    *,
    coverage_days: int,
    window_days: int,
) -> dict[str, Any]:
    """Say whether there is enough to work on, and where the movement is if there is not.

    It recommends; it never changes the focus. A thin bucket may be the right focus
    (a client priority that needs new pages), and the advice says that too.
    """
    if window_days and coverage_days < window_days * MIN_COVERAGE_SHARE:
        return {
            "level": "thin_data",
            "headline": "Not enough Search Console history to trust this list.",
            "reasons": [
                f"Search Console has {coverage_days} days of data in the {window_days}-day window. "
                "Positions and impressions from so few days can swing the ranking of every row."
            ],
            "suggestions": [{"kind": "data", "text": "Pull more Search Console history, then read the list again."}],
        }

    focus = next((b for b in buckets if b["id"] == focus_bucket_id), None)
    if focus is None:
        return {"level": "ok", "headline": "", "reasons": [], "suggestions": []}

    others = sorted(
        (b for b in buckets if b["id"] != focus["id"] and b["strong"] > 0),
        key=lambda b: b["expected_extra_clicks"],
        reverse=True,
    )
    if focus["reach"] != "thin":
        return {
            "level": "ok",
            "headline": f"{focus['name']} has enough to work with.",
            "reasons": [f"{focus['strong']} strong and {focus['possible']} possible searches are in reach."],
            "suggestions": [],
        }

    reasons = [
        f"{focus['found']} {'search' if focus['found'] == 1 else 'searches'} in reach, none strong, "
        f"for a possible +{focus['expected_extra_clicks']:g} clicks."
    ]
    if focus["unranked_terms"]:
        reasons.append(f"{focus['unranked_terms']} of its {focus['terms']} terms have no Google impressions at all.")
    reasons.append("No page ranks well enough to nudge, so moving this bucket means writing pages for it.")

    suggestions: list[dict[str, Any]] = [
        {
            "kind": "bucket",
            "bucket_id": b["id"],
            "name": b["name"],
            "text": f"{b['name']}: {b['strong']} strong, +{b['expected_extra_clicks']:g} extra clicks in the top 20.",
        }
        for b in others[:2]
    ]
    if others:
        headline = f"Shift Visibility to {others[0]['name']}, or treat {focus['name']} as a content job."
    else:
        headline = f"Nothing in any bucket is close enough to move. Treat {focus['name']} as a content job, or pick a different focus."
        suggestions.append({"kind": "focus", "text": "Visibility has little to move on any bucket; consider Traffic or Leads."})
    suggestions.append(
        {"kind": "content", "text": f"Keep {focus['name']} as the focus and plan new pages for its terms (Content hub, later)."}
    )
    return {"level": "shift", "headline": headline, "reasons": reasons, "suggestions": suggestions}


def bucket_overview(db: Session, client: Client, month: str, focus_bucket_id: str | None = None) -> dict[str, Any]:
    """Each bucket in one line, and advice on the focus: is there enough here to work on?"""
    buckets = (
        db.query(WatchlistBucket)
        .filter(WatchlistBucket.client_id == client.id)
        .order_by(WatchlistBucket.sort_order, WatchlistBucket.name)
        .all()
    )
    rows = []
    for bucket in buckets:
        result = build(db, client, month, bucket.id)
        terms = len(result["bucket"]["terms"]) if result["bucket"] else 0
        rows.append(
            {
                "id": str(bucket.id),
                "name": bucket.name,
                "terms": terms,
                "found": result["counts"]["found"],
                "strong": result["counts"]["strong"],
                "possible": result["counts"]["possible"],
                "expected_extra_clicks": round(sum(c["expected_extra_clicks"] for c in result["candidates"]), 1),
                "unranked_terms": len(result["unranked"]),
                "reach": reach_label(result["counts"]["strong"], result["counts"]["found"]),
            }
        )

    year, mon = int(month[:4]), int(month[5:7])
    start, end = windows(date(year, mon, 1))["current"]
    coverage = (
        db.query(func.count(func.distinct(FactGscDaily.date)))
        .filter(FactGscDaily.client_id == client.id, FactGscDaily.date >= start, FactGscDaily.date <= end)
        .scalar()
        or 0
    )
    window_days = (end - start).days + 1
    return {
        "buckets": rows,
        "coverage": {"days": int(coverage), "window_days": window_days},
        "advice": advise(rows, focus_bucket_id, coverage_days=int(coverage), window_days=window_days),
    }
