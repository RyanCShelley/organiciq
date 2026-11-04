"""Search visibility: where the watchlist's terms show in Google, Bing and SE Ranking, and whether the three agree.

A term is matched to a search query exactly (lower-cased), as in the monthly review, so a longer phrase the site also
shows for does not count toward the term. Positions are impression-weighted averages over the range; a position needs at
least MIN_IMPRESSIONS behind it to be believed. SE Ranking gives one position a day for the keywords it tracks.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerCompetitorKeyword, FactSerRanking, FactSerpFeature
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services import google_updates
from app.services.review_visibility import MIN_IMPRESSIONS_FOR_POSITION, _bing, _google, key_of

#: Sources further apart than this many positions are said to disagree.
DISAGREE_BY = 5
WEEKS_SHOWN = 26
MOVERS_SHOWN = 6


def previous_range(start: date, end: date) -> tuple[date, date]:
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def _believed(row: dict | None) -> float | None:
    """A Search Console or Bing position, only when enough impressions stand behind it."""
    if not row or (row.get("impressions") or 0) < MIN_IMPRESSIONS_FOR_POSITION:
        return None
    return row.get("position")


def band(position: float | None) -> str:
    if position is None:
        return "none"
    return "top3" if position <= 3 else "top10" if position <= 10 else "top20" if position <= 20 else "beyond"


def watchlist_terms(db: Session, client: Client, bucket_id: str | None = None) -> list[dict[str, Any]]:
    q = (
        db.query(WatchlistKeyword.keyword, WatchlistKeyword.volume, WatchlistBucket.id, WatchlistBucket.name)
        .join(WatchlistBucket, WatchlistBucket.id == WatchlistKeyword.bucket_id)
        .filter(WatchlistKeyword.client_id == client.id)
    )
    if bucket_id:
        q = q.filter(WatchlistBucket.id == bucket_id)
    return [{"term": k, "key": key_of(k), "volume": v, "bucket_id": str(bid), "bucket": name} for k, v, bid, name in q.order_by(WatchlistBucket.sort_order, WatchlistKeyword.keyword)]


def _ser(db: Session, client: Client, keys: list[str], start: date, end: date) -> dict[str, dict]:
    """SE Ranking's position for each tracked keyword on the first and last day it checked in the range."""
    days = [d for (d,) in db.query(FactSerRanking.date).filter(FactSerRanking.client_id == client.id, FactSerRanking.date >= start, FactSerRanking.date <= end).distinct().order_by(FactSerRanking.date)]
    if not days:
        return {}
    first, last = days[0], days[-1]
    q = func.lower(func.trim(FactSerRanking.keyword))
    out: dict[str, dict] = {}
    for k, day, pos, vol, url in db.query(q, FactSerRanking.date, FactSerRanking.position, FactSerRanking.volume, FactSerRanking.ranking_url).filter(
        FactSerRanking.client_id == client.id, FactSerRanking.date.in_([first, last]), q.in_(keys)
    ):
        item = out.setdefault(key_of(k), {"start": None, "end": None, "volume": None, "url": None, "from": first.isoformat(), "to": last.isoformat()})
        p = float(pos) if pos else None  # 0 or missing: not ranking
        if day == first:
            item["start"] = p
        if day == last:
            item["end"], item["url"] = p, url or None
            item["volume"] = float(vol) if vol is not None else None
    return out


def _weekly(db: Session, client: Client, keys: list[str], start: date, end: date) -> tuple[list[str], dict[str, list[float | None]], list[dict]]:
    """Weeks of the range (Monday first): each term's impression-weighted position, and the whole watchlist's impressions, clicks and position."""
    week = func.date_trunc("week", FactGscQueryPage.date)
    q = func.lower(func.trim(FactGscQueryPage.query))
    rows = (
        db.query(
            week, q,
            func.sum(FactGscQueryPage.impressions), func.sum(FactGscQueryPage.clicks),
            func.sum(FactGscQueryPage.average_position * FactGscQueryPage.impressions),
        )
        .filter(FactGscQueryPage.client_id == client.id, FactGscQueryPage.date >= start, FactGscQueryPage.date <= end, q.in_(keys))
        .group_by(week, q)
        .all()
    )
    weeks = sorted({w.date().isoformat() for w, *_ in rows})[-WEEKS_SHOWN:]
    index = {w: i for i, w in enumerate(weeks)}
    per_term: dict[str, list[float | None]] = defaultdict(lambda: [None] * len(weeks))
    total = [{"week": w, "impressions": 0.0, "clicks": 0.0, "weighted": 0.0} for w in weeks]
    for w, k, imp, clk, weighted in rows:
        i = index.get(w.date().isoformat())
        if i is None:
            continue
        imp, clk, weighted = float(imp or 0), float(clk or 0), float(weighted or 0)
        if imp >= 1:
            per_term[key_of(k)][i] = round(weighted / imp, 1)
        total[i]["impressions"] += imp
        total[i]["clicks"] += clk
        total[i]["weighted"] += weighted
    series = [
        {"week": t["week"], "impressions": round(t["impressions"]), "clicks": round(t["clicks"]), "position": round(t["weighted"] / t["impressions"], 1) if t["impressions"] else None}
        for t in total
    ]
    return weeks, dict(per_term), series


def _disagreement(google: float | None, bing: float | None, ser: float | None) -> str | None:
    shown = {name: p for name, p in (("Google", google), ("Bing", bing), ("SE Ranking", ser)) if p is not None}
    if len(shown) < 2:
        return None
    low, high = min(shown, key=shown.get), max(shown, key=shown.get)
    if shown[high] - shown[low] >= DISAGREE_BY:
        return f"{low} has it at {shown[low]:g}, {high} at {shown[high]:g}"
    return None


def build(db: Session, client: Client, start: date, end: date, bucket_id: str | None = None) -> dict[str, Any]:
    terms = watchlist_terms(db, client, bucket_id)
    keys = [t["key"] for t in terms]
    ps, pe = previous_range(start, end)
    google, google_before = (_google(db, client, keys, start, end), _google(db, client, keys, ps, pe)) if keys else ({}, {})
    bing = _bing(db, client, keys, start, end) if keys else {}
    ser = _ser(db, client, keys, start, end) if keys else {}
    weeks, per_term, series = _weekly(db, client, keys, start, end) if keys else ([], {}, [])

    rows = []
    for t in terms:
        k = t["key"]
        g, gb, b = google.get(k), google_before.get(k), bing.get(k)
        gpos, gprev, bpos = _believed(g), _believed(gb), _believed(b)
        s = ser.get(k) or {}
        spos = s.get("end")
        # Positive: moved up. Google first, SE Ranking when Google has too little to say.
        move = round(gprev - gpos, 1) if gpos is not None and gprev is not None else round(s["start"] - s["end"], 1) if s.get("start") is not None and s.get("end") is not None else None
        rows.append(
            {
                **t,
                "google": {"impressions": round((g or {}).get("impressions") or 0), "clicks": round((g or {}).get("clicks") or 0), "position": gpos, "position_before": gprev},
                "bing": {"impressions": round((b or {}).get("impressions") or 0), "clicks": round((b or {}).get("clicks") or 0), "position": bpos},
                "ser": {"position": spos, "position_start": s.get("start"), "tracked": k in ser, "url": s.get("url")},
                "best": gpos if gpos is not None else spos if spos is not None else bpos,
                "band": band(gpos if gpos is not None else spos if spos is not None else bpos),
                "move": move,
                "disagree": _disagreement(gpos, bpos, spos),
                "trend": per_term.get(k, []),
            }
        )
    rows.sort(key=lambda r: (-(r["google"]["impressions"] or 0), r["term"]))

    def totals(source: dict[str, dict]) -> dict[str, Any]:
        shown = [v for k, v in source.items() if (v.get("impressions") or 0) > 0]
        imp = sum(v["impressions"] for v in shown)
        weighted = sum((v["position"] or 0) * v["impressions"] for v in shown if v.get("position") is not None)
        page_one = sum(1 for v in shown if _believed(v) is not None and _believed(v) <= 10)
        return {"showing": len(shown), "page_one": page_one, "clicks": round(sum(v["clicks"] for v in shown)), "impressions": round(imp), "position": round(weighted / imp, 1) if imp else None}

    distribution = {"now": defaultdict(int), "before": defaultdict(int)}
    for r in rows:
        distribution["now"][band(r["google"]["position"])] += 1
        distribution["before"][band(r["google"]["position_before"])] += 1
    ranked = [r for r in rows if r["move"] is not None and abs(r["move"]) >= 0.5]
    return {
        "from": start.isoformat(), "to": end.isoformat(),
        "buckets": [{"id": str(b.id), "name": b.name} for b in db.query(WatchlistBucket).filter(WatchlistBucket.client_id == client.id).order_by(WatchlistBucket.sort_order)],
        "terms_total": len(terms),
        "now": totals(google), "before": totals(google_before),
        "distribution": {"now": dict(distribution["now"]), "before": dict(distribution["before"])},
        "weeks": weeks, "series": series,
        "winners": sorted((r for r in ranked if r["move"] > 0), key=lambda r: -r["move"])[:MOVERS_SHOWN],
        "losers": sorted((r for r in ranked if r["move"] < 0), key=lambda r: r["move"])[:MOVERS_SHOWN],
        "terms": rows,
        "updates": google_updates.between(db, start, end),
        "sources": {"ser_tracked": len(ser), "bing_terms": len([1 for v in bing.values() if (v.get("impressions") or 0) > 0]), "ser_from": next((v["from"] for v in ser.values()), None), "ser_to": next((v["to"] for v in ser.values()), None)},
    }


def term_detail(db: Session, client: Client, term: str, start: date, end: date) -> dict[str, Any]:
    key = key_of(term)
    q = func.lower(func.trim(FactGscQueryPage.query))
    pages = [
        {"url": url, "impressions": round(float(i or 0)), "clicks": round(float(c or 0)), "position": round(float(w or 0) / float(i), 1) if i else None}
        for url, i, c, w in db.query(
            FactGscQueryPage.normalized_url, func.sum(FactGscQueryPage.impressions), func.sum(FactGscQueryPage.clicks), func.sum(FactGscQueryPage.average_position * FactGscQueryPage.impressions)
        ).filter(FactGscQueryPage.client_id == client.id, q == key, FactGscQueryPage.date >= start, FactGscQueryPage.date <= end).group_by(FactGscQueryPage.normalized_url).order_by(func.sum(FactGscQueryPage.impressions).desc()).limit(10)
    ]
    ck = func.lower(func.trim(FactSerCompetitorKeyword.keyword))
    newest = db.query(func.max(FactSerCompetitorKeyword.fetched_at)).filter(FactSerCompetitorKeyword.client_id == client.id, ck == key).scalar()
    competitors = (
        [{"domain": d, "position": float(p), "url": u} for d, p, u in db.query(FactSerCompetitorKeyword.competitor_domain, FactSerCompetitorKeyword.position, FactSerCompetitorKeyword.ranking_url).filter(
            FactSerCompetitorKeyword.client_id == client.id, ck == key, FactSerCompetitorKeyword.fetched_at == newest).order_by(FactSerCompetitorKeyword.position).limit(10)]
        if newest else []
    )
    fk = func.lower(func.trim(FactSerpFeature.keyword))
    feature = db.query(FactSerpFeature).filter(FactSerpFeature.client_id == client.id, fk == key).order_by(FactSerpFeature.pulled_on.desc()).first()
    return {
        "term": term, "pages": pages, "competitors": competitors, "competitors_read_on": newest.isoformat() if newest else None,
        "serp": {"pulled_on": feature.pulled_on.isoformat(), "features": list(feature.item_types or []), "holders": feature.holders or {}} if feature else None,
    }
