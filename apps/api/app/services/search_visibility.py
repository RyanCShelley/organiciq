"""Search visibility: where the watchlist's terms show in Google, Bing and SE Ranking, and whether the three agree.

A term is matched to a search query exactly (lower-cased), as in the monthly review, so a longer phrase the site also
shows for does not count toward the term. Positions are impression-weighted averages over the range; a position needs at
least MIN_IMPRESSIONS behind it to be believed. SE Ranking gives one position a day for the keywords it tracks.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.decisions.content_gaps import content_words
from app.decisions.visibility_candidates import brand_keys, is_brand
from app.models.annotation import Annotation
from app.models.bing_stats import FactBingQueryStat
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerCompetitorKeyword, FactSerRanking, FactSerpFeature
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services import google_updates
from app.services.review_visibility import MIN_IMPRESSIONS_FOR_POSITION, _bing, _google, key_of

#: Sources further apart than this many positions are said to disagree.
DISAGREE_BY = 5
WEEKS_SHOWN = 26
MOVERS_SHOWN = 6

UNSUNG_MIN_IMPRESSIONS = 25
UNSUNG_HIGH_IMPRESSIONS = 100
UNSUNG_FALLBACK_MIN_IMPRESSIONS = 100
UNSUNG_RISING_PCT = 25.0
UNSUNG_RISING_DELTA = 20
UNSUNG_RISING_POS_MOVE = 2.0
UNSUNG_HEROES_SHOWN = 25

ANNOTATION_TYPE_LABELS = {
    "growth_action": "Growth action",
    "event": "Event or trade show",
    "content_published": "New content",
    "content_updated": "Content change",
    "technical_change": "Technical change",
    "website_change": "Website change",
    "conversion_change": "Conversion change",
    "campaign_change": "Campaign change",
    "algorithm_event": "Search update",
    "visibility_check": "Visibility check",
    "manual_note": "Note",
}


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


def _bing_all(db: Session, client: Client, first: date, last: date) -> dict[str, dict]:
    """All Bing queries for the client in [first, last], not limited to the watchlist."""
    pos_imp = case(
        (FactBingQueryStat.avg_impression_position.isnot(None), FactBingQueryStat.impressions),
        else_=0,
    )
    rows = (
        db.query(
            FactBingQueryStat.query_key,
            func.sum(FactBingQueryStat.impressions),
            func.sum(FactBingQueryStat.clicks),
            func.sum(FactBingQueryStat.avg_impression_position * FactBingQueryStat.impressions),
            func.sum(pos_imp),
        )
        .filter(
            FactBingQueryStat.client_id == client.id,
            FactBingQueryStat.week_start >= first,
            FactBingQueryStat.week_start <= last,
        )
        .group_by(FactBingQueryStat.query_key)
        .all()
    )
    out: dict[str, dict] = {}
    for k, impressions, clicks, weighted, p_imp in rows:
        imp_f = float(impressions or 0)
        p_imp_f = float(p_imp or 0)
        key = key_of(k)
        cur = out.setdefault(key, {"impressions": 0.0, "clicks": 0.0, "_weighted": 0.0, "_p_imp": 0.0})
        cur["impressions"] += imp_f
        cur["clicks"] += float(clicks or 0)
        cur["_weighted"] += float(weighted or 0)
        cur["_p_imp"] += p_imp_f
    return {
        k: {
            "impressions": v["impressions"],
            "clicks": v["clicks"],
            "position": round(v["_weighted"] / v["_p_imp"], 1) if v["_p_imp"] else None,
        }
        for k, v in out.items()
    }


def _bing_weekly(
    db: Session, client: Client, keys: list[str] | None, start: date, end: date
) -> dict[str, dict[str, Any]]:
    """Weekly Bing totals truncated to Monday so they align with GSC weeks."""
    if keys is not None and not keys:
        return {}
    week = func.date_trunc("week", FactBingQueryStat.week_start)
    pos_imp = case(
        (FactBingQueryStat.avg_impression_position.isnot(None), FactBingQueryStat.impressions),
        else_=0,
    )
    query = db.query(
        week,
        func.sum(FactBingQueryStat.impressions),
        func.sum(FactBingQueryStat.clicks),
        func.sum(FactBingQueryStat.avg_impression_position * FactBingQueryStat.impressions),
        func.sum(pos_imp),
    ).filter(
        FactBingQueryStat.client_id == client.id,
        FactBingQueryStat.week_start >= start,
        FactBingQueryStat.week_start <= end,
    )
    if keys is not None:
        query = query.filter(FactBingQueryStat.query_key.in_(keys))
    rows = query.group_by(week).all()
    out: dict[str, dict[str, Any]] = {}
    for w, imp, clk, weighted, p_imp in rows:
        w_iso = w.date().isoformat()
        imp_f = float(imp or 0)
        clk_f = float(clk or 0)
        p_imp_f = float(p_imp or 0)
        weighted_f = float(weighted or 0)
        pos = round(weighted_f / p_imp_f, 1) if p_imp_f >= MIN_IMPRESSIONS_FOR_POSITION else None
        out[w_iso] = {"impressions": round(imp_f), "clicks": round(clk_f), "position": pos}
    return out


def _weekly(
    db: Session, client: Client, keys: list[str], start: date, end: date
) -> tuple[list[str], dict[str, dict[str, float | None]], dict[str, dict[str, Any]]]:
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
    per_term: dict[str, dict[str, float | None]] = defaultdict(dict)
    total: dict[str, dict[str, float]] = {
        w: {"impressions": 0.0, "clicks": 0.0, "weighted": 0.0} for w in weeks
    }
    week_set = set(weeks)
    for w, k, imp, clk, weighted in rows:
        w_iso = w.date().isoformat()
        if w_iso not in week_set:
            continue
        imp_f, clk_f, weighted_f = float(imp or 0), float(clk or 0), float(weighted or 0)
        if imp_f >= 1:
            per_term[key_of(k)][w_iso] = round(weighted_f / imp_f, 1)
        total[w_iso]["impressions"] += imp_f
        total[w_iso]["clicks"] += clk_f
        total[w_iso]["weighted"] += weighted_f
    series_map = {
        w: {
            "week": w,
            "impressions": round(t["impressions"]),
            "clicks": round(t["clicks"]),
            "position": round(t["weighted"] / t["impressions"], 1) if t["impressions"] else None,
        }
        for w, t in total.items()
    }
    return weeks, dict(per_term), series_map


def _unsung_heroes(
    db: Session, client: Client, start: date, end: date, ps: date, pe: date
) -> list[dict[str, Any]]:
    """Surface relevant, non-brand, high-impression or rising GSC queries not currently on the watchlist."""
    watch_rows = (
        db.query(WatchlistKeyword.keyword, WatchlistKeyword.keyword_key)
        .filter(WatchlistKeyword.client_id == client.id)
        .all()
    )
    all_watch_keys = {key_of(kw) for kw, _ in watch_rows if kw} | {
        key_of(kk) for _, kk in watch_rows if kk
    }
    watchlist_tokens = content_words(" ".join(kw for kw, _ in watch_rows if kw))

    crawl_rows = (
        db.query(
            FactCrawlPageSnapshot.title,
            FactCrawlPageSnapshot.normalized_url,
            FactCrawlPageSnapshot.sections,
        )
        .filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlPageSnapshot.indexable.is_(True),
        )
        .all()
    )
    crawl_tokens: frozenset[str] = (
        frozenset().union(
            *(
                content_words(
                    " ".join(
                        [
                            r.title or "",
                            urlsplit(r.normalized_url).path,
                            *(
                                str(s.get("heading") or "")
                                for s in (r.sections or [])
                                if isinstance(s, dict)
                            ),
                        ]
                    )
                )
                for r in crawl_rows
            )
        )
        if crawl_rows
        else frozenset()
    )
    site_tokens = watchlist_tokens | crawl_tokens
    b_keys = brand_keys(client)

    q_norm = func.lower(func.trim(FactGscQueryPage.query))
    now_rows = (
        db.query(
            q_norm,
            FactGscQueryPage.normalized_url,
            func.min(FactGscQueryPage.query),
            func.sum(FactGscQueryPage.impressions),
            func.sum(FactGscQueryPage.clicks),
            func.sum(FactGscQueryPage.average_position * FactGscQueryPage.impressions),
        )
        .filter(
            FactGscQueryPage.client_id == client.id,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= end,
        )
        .group_by(q_norm, FactGscQueryPage.normalized_url)
        .all()
    )

    now_agg: dict[str, dict[str, Any]] = {}
    for norm_q, page_url, raw_q, imp, clk, weighted in now_rows:
        k = key_of(norm_q)
        if not k or k in all_watch_keys or is_brand(k, b_keys):
            continue
        imp_f = float(imp or 0)
        clk_f = float(clk or 0)
        weighted_f = float(weighted or 0)
        cur = now_agg.get(k)
        if cur is None:
            now_agg[k] = {
                "query": raw_q or k,
                "impressions": imp_f,
                "clicks": clk_f,
                "weighted": weighted_f,
                "best_page": page_url,
                "best_page_imp": imp_f,
            }
        else:
            cur["impressions"] += imp_f
            cur["clicks"] += clk_f
            cur["weighted"] += weighted_f
            if (imp_f, page_url or "") > (cur["best_page_imp"], cur["best_page"] or ""):
                cur["best_page"] = page_url
                cur["best_page_imp"] = imp_f
                if raw_q:
                    cur["query"] = raw_q

    candidates = {
        k: v for k, v in now_agg.items() if v["impressions"] >= UNSUNG_MIN_IMPRESSIONS
    }
    if not candidates:
        return []

    has_prior_gsc = (
        db.query(FactGscQueryPage.id)
        .filter(
            FactGscQueryPage.client_id == client.id,
            FactGscQueryPage.date >= ps,
            FactGscQueryPage.date <= pe,
        )
        .first()
        is not None
    )
    prev_agg: dict[str, dict[str, float]] = {}
    if has_prior_gsc:
        prev_rows = (
            db.query(
                q_norm,
                func.sum(FactGscQueryPage.impressions),
                func.sum(FactGscQueryPage.clicks),
                func.sum(FactGscQueryPage.average_position * FactGscQueryPage.impressions),
            )
            .filter(
                FactGscQueryPage.client_id == client.id,
                FactGscQueryPage.date >= ps,
                FactGscQueryPage.date <= pe,
            )
            .group_by(q_norm)
            .all()
        )
        for norm_q, imp, clk, weighted in prev_rows:
            k = key_of(norm_q)
            if k not in candidates:
                continue
            cur = prev_agg.setdefault(k, {"impressions": 0.0, "clicks": 0.0, "weighted": 0.0})
            cur["impressions"] += float(imp or 0)
            cur["clicks"] += float(clk or 0)
            cur["weighted"] += float(weighted or 0)

    heroes: list[dict[str, Any]] = []
    for k, now in candidates.items():
        imp = round(now["impressions"])
        clk = round(now["clicks"])
        pos_now = (
            round(now["weighted"] / now["impressions"], 1)
            if now["impressions"] >= MIN_IMPRESSIONS_FOR_POSITION
            else None
        )
        prev = prev_agg.get(k)
        imp_before = round(prev["impressions"]) if prev else 0
        pos_before = (
            round(prev["weighted"] / prev["impressions"], 1)
            if prev and prev["impressions"] >= MIN_IMPRESSIONS_FOR_POSITION
            else None
        )
        imp_change_pct = (
            round((imp - imp_before) / imp_before * 100, 1) if imp_before > 0 else None
        )
        move = (
            round(pos_before - pos_now, 1)
            if pos_now is not None and pos_before is not None
            else None
        )
        ctr = round((clk / imp) * 100, 1) if imp > 0 else None

        is_high = imp >= UNSUNG_HIGH_IMPRESSIONS
        is_new = has_prior_gsc and imp_before == 0 and imp >= UNSUNG_MIN_IMPRESSIONS
        is_rising = (
            imp_before > 0
            and (imp - imp_before) >= UNSUNG_RISING_DELTA
            and (imp_change_pct or 0.0) >= UNSUNG_RISING_PCT
        ) or (move is not None and move >= UNSUNG_RISING_POS_MOVE)
        if not (is_high or is_new or is_rising):
            continue

        q_tokens = content_words(k)
        watch_hits = sorted(q_tokens & watchlist_tokens)
        crawl_hits = sorted(q_tokens & crawl_tokens)
        has_overlap = bool(watch_hits or crawl_hits)
        if not has_overlap and site_tokens:
            if not (
                len(q_tokens) >= 2
                and imp >= UNSUNG_FALLBACK_MIN_IMPRESSIONS
                and ((pos_now is not None and pos_now <= 20.0) or clk >= 2)
            ):
                continue

        signals: list[str] = []
        if is_high:
            signals.append("high_impressions")
        if is_rising:
            signals.append("rising")
        if is_new:
            signals.append("new")
        if has_overlap:
            signals.append("relevant")

        if watch_hits and crawl_hits:
            combined = (watch_hits + [w for w in crawl_hits if w not in watch_hits])[:3]
            relevance_note = f"Matches watchlist & site content ({', '.join(combined)})"
        elif watch_hits:
            relevance_note = f"Matches watchlist topic ({', '.join(watch_hits[:3])})"
        elif crawl_hits:
            relevance_note = f"Matches site content ({', '.join(crawl_hits[:3])})"
        elif is_high:
            relevance_note = "High-impression non-brand search"
        else:
            relevance_note = "Rising non-brand search"

        score = (2.0 if has_overlap else 1.0) * (
            imp
            + (clk * 10)
            + (max(0, imp - imp_before) if imp_before > 0 else 0)
            + (50 if is_rising else 0)
        )
        heroes.append(
            {
                "query": now["query"],
                "key": k,
                "page": now["best_page"],
                "impressions": imp,
                "impressions_before": imp_before,
                "impressions_change_pct": imp_change_pct,
                "clicks": clk,
                "position": pos_now,
                "position_before": pos_before,
                "move": move,
                "ctr": ctr,
                "signals": signals,
                "relevance_note": relevance_note,
                "_score": score,
            }
        )

    heroes.sort(key=lambda item: (-item["_score"], -item["impressions"], item["key"]))
    for item in heroes:
        item.pop("_score", None)
    return heroes[:UNSUNG_HEROES_SHOWN]


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
    bing_before = _bing(db, client, keys, ps, pe) if keys else {}
    ser = _ser(db, client, keys, start, end) if keys else {}

    gsc_weeks, gsc_per_term, gsc_series_map = _weekly(db, client, keys, start, end) if keys else ([], {}, {})
    bing_watch_weekly = _bing_weekly(db, client, keys, start, end) if keys else {}
    bing_site_weekly = _bing_weekly(db, client, None, start, end)
    bing_active_weekly = bing_watch_weekly if bing_watch_weekly else bing_site_weekly
    bing_series_scope = "watchlist" if bing_watch_weekly else ("site" if bing_site_weekly else "none")
    weeks = sorted(set(gsc_weeks) | set(bing_active_weekly.keys()))[-WEEKS_SHOWN:]

    per_term: dict[str, list[float | None]] = {
        k: [gsc_per_term.get(k, {}).get(w) for w in weeks]
        for k in keys
    }
    series = (
        [
            gsc_series_map.get(w, {"week": w, "impressions": 0, "clicks": 0, "position": None})
            for w in weeks
        ]
        if gsc_weeks
        else []
    )
    bing_series = (
        [
            {"week": w, **bing_active_weekly.get(w, {"impressions": 0, "clicks": 0, "position": None})}
            for w in weeks
        ]
        if bing_active_weekly
        else []
    )

    rows = []
    for t in terms:
        k = t["key"]
        g, gb, b, bb = google.get(k), google_before.get(k), bing.get(k), bing_before.get(k)
        gpos, gprev, bpos, bprev = _believed(g), _believed(gb), _believed(b), _believed(bb)
        bmove = round(bprev - bpos, 1) if bpos is not None and bprev is not None else None
        s = ser.get(k) or {}
        spos = s.get("end")
        # Positive: moved up. Google first, SE Ranking when Google has too little to say.
        move = round(gprev - gpos, 1) if gpos is not None and gprev is not None else round(s["start"] - s["end"], 1) if s.get("start") is not None and s.get("end") is not None else None
        rows.append(
            {
                **t,
                "google": {"impressions": round((g or {}).get("impressions") or 0), "clicks": round((g or {}).get("clicks") or 0), "position": gpos, "position_before": gprev},
                "bing": {
                    "impressions": round((b or {}).get("impressions") or 0),
                    "clicks": round((b or {}).get("clicks") or 0),
                    "position": bpos,
                    "position_before": bprev,
                    "move": bmove,
                },
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
        shown = [v for v in source.values() if (v.get("impressions") or 0) > 0]
        imp = sum(v["impressions"] for v in shown)
        pos_imp = sum(v["impressions"] for v in shown if v.get("position") is not None)
        weighted = sum((v["position"] or 0) * v["impressions"] for v in shown if v.get("position") is not None)
        page_one = sum(1 for v in shown if _believed(v) is not None and _believed(v) <= 10)
        return {"showing": len(shown), "page_one": page_one, "clicks": round(sum(v["clicks"] for v in shown)), "impressions": round(imp), "position": round(weighted / pos_imp, 1) if pos_imp else None}

    distribution = {"now": defaultdict(int), "before": defaultdict(int)}
    for r in rows:
        distribution["now"][band(r["google"]["position"])] += 1
        distribution["before"][band(r["google"]["position_before"])] += 1
    ranked = [r for r in rows if r["move"] is not None and abs(r["move"]) >= 0.5]
    bing_ranked = [r for r in rows if r["bing"]["move"] is not None and abs(r["bing"]["move"]) >= 0.5]
    bing_winners = sorted((r for r in bing_ranked if r["bing"]["move"] > 0), key=lambda r: -r["bing"]["move"])[:MOVERS_SHOWN]
    bing_losers = sorted((r for r in bing_ranked if r["bing"]["move"] < 0), key=lambda r: r["bing"]["move"])[:MOVERS_SHOWN]

    bing_site_now_map = _bing_all(db, client, start, end)
    bing_site_before_map = _bing_all(db, client, ps, pe)
    bing_site_now = totals(bing_site_now_map)
    bing_site_before = totals(bing_site_before_map)

    # The newest day Search Console / Bing has reported for this client, whatever range is on screen.
    google_through = db.query(func.max(FactGscQueryPage.date)).filter(FactGscQueryPage.client_id == client.id).scalar()
    bing_through = db.query(func.max(FactBingQueryStat.week_start)).filter(FactBingQueryStat.client_id == client.id).scalar()

    annotations_out = [
        {
            "id": str(a.id),
            "date": a.date.isoformat(),
            "type": a.annotation_type.value,
            "type_label": ANNOTATION_TYPE_LABELS.get(a.annotation_type.value, a.annotation_type.value),
            "description": a.description,
            "notes": a.notes,
        }
        for a in db.query(Annotation)
        .filter(Annotation.client_id == client.id, Annotation.date >= start, Annotation.date <= end)
        .order_by(Annotation.date.desc(), Annotation.created_at.desc())
        .all()
    ]

    return {
        "from": start.isoformat(), "to": end.isoformat(),
        "buckets": [{"id": str(b.id), "name": b.name} for b in db.query(WatchlistBucket).filter(WatchlistBucket.client_id == client.id).order_by(WatchlistBucket.sort_order)],
        "terms_total": len(terms),
        "now": totals(google), "before": totals(google_before),
        "bing_now": totals(bing),
        "bing_before": totals(bing_before),
        "bing_site": {"now": bing_site_now, "before": bing_site_before},
        "distribution": {"now": dict(distribution["now"]), "before": dict(distribution["before"])},
        "weeks": weeks, "series": series,
        "bing_series": bing_series,
        "bing_series_scope": bing_series_scope,
        "winners": sorted((r for r in ranked if r["move"] > 0), key=lambda r: -r["move"])[:MOVERS_SHOWN],
        "losers": sorted((r for r in ranked if r["move"] < 0), key=lambda r: r["move"])[:MOVERS_SHOWN],
        "bing_winners": bing_winners,
        "bing_losers": bing_losers,
        "terms": rows,
        "unsung_heroes": _unsung_heroes(db, client, start, end, ps, pe),
        "annotations": annotations_out,
        "updates": google_updates.between(db, start, end),
        "sources": {
            "google_through": google_through.isoformat() if google_through else None,
            "ser_tracked": len(ser),
            "bing_terms": len([1 for v in bing.values() if (v.get("impressions") or 0) > 0]),
            "has_bing": bing_through is not None,
            "bing_through": bing_through.isoformat() if bing_through else None,
            "bing_site_terms": bing_site_now["showing"],
            "ser_from": next((v["from"] for v in ser.values()), None),
            "ser_to": next((v["to"] for v in ser.values()), None),
        },
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
