"""How the watchlist terms are showing in Google and Bing, month against month.

Sources are Search Console (daily) and Bing Webmaster (weekly). A term is matched to
a search query exactly (lower-cased), so a variant the site shows for does not count
toward the term: the numbers say how the term itself performs, and understate it where
people search a longer phrase. SE Ranking is deliberately not used here.

AI results come from the client's LLM visibility runs: for each term, whether the AI platforms
named or cited the brand when asked its paired prompt, across every run in the month, pooled (or, if none was
done that month, the latest run, labelled as such).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.bing_stats import FactBingQueryStat
from app.models.client import Client
from app.models.gsc import FactGscQueryPage
from app.models.llm_visibility import LlmResponse, LlmRun
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services.monthly_review import parse_month, pct_change, previous_month

#: Under this many impressions in a month, an average position says nothing.
MIN_IMPRESSIONS_FOR_POSITION = 10


def key_of(term: str) -> str:
    return " ".join((term or "").lower().split())


def _blank() -> dict[str, float | None]:
    return {"impressions": 0.0, "clicks": 0.0, "position": None}


def _google(db: Session, client: Client, keys: list[str], first: date, last: date) -> dict[str, dict]:
    q = func.lower(func.trim(FactGscQueryPage.query))
    rows = (
        db.query(
            q.label("k"),
            func.sum(FactGscQueryPage.impressions),
            func.sum(FactGscQueryPage.clicks),
            func.sum(FactGscQueryPage.average_position * FactGscQueryPage.impressions),
        )
        .filter(
            FactGscQueryPage.client_id == client.id,
            FactGscQueryPage.date >= first,
            FactGscQueryPage.date <= last,
            q.in_(keys),
        )
        .group_by("k")
        .all()
    )
    out: dict[str, dict] = {}
    for k, impressions, clicks, weighted in rows:
        impressions = float(impressions or 0)
        out[key_of(k)] = {
            "impressions": impressions,
            "clicks": float(clicks or 0),
            "position": round(float(weighted or 0) / impressions, 1) if impressions else None,
        }
    return out


def _bing(db: Session, client: Client, keys: list[str], first: date, last: date) -> dict[str, dict]:
    """Weeks that start inside the month. Bing's weeks straddle month ends, so the edges are approximate."""
    rows = (
        db.query(
            FactBingQueryStat.query_key,
            func.sum(FactBingQueryStat.impressions),
            func.sum(FactBingQueryStat.clicks),
            func.sum(FactBingQueryStat.avg_impression_position * FactBingQueryStat.impressions),
        )
        .filter(
            FactBingQueryStat.client_id == client.id,
            FactBingQueryStat.week_start >= first,
            FactBingQueryStat.week_start <= last,
            FactBingQueryStat.query_key.in_(keys),
        )
        .group_by(FactBingQueryStat.query_key)
        .all()
    )
    out: dict[str, dict] = {}
    for k, impressions, clicks, weighted in rows:
        impressions = float(impressions or 0)
        out[key_of(k)] = {
            "impressions": impressions,
            "clicks": float(clicks or 0),
            "position": round(float(weighted or 0) / impressions, 1) if impressions else None,
        }
    return out


def _pair(current: float | None, previous: float | None) -> dict[str, float | None]:
    return {"current": current, "previous": previous, "change_pct": pct_change(current, previous)}


def _engine(now: dict | None, then: dict | None) -> dict[str, Any]:
    now, then = now or _blank(), then or _blank()
    return {
        "impressions": _pair(now["impressions"], then["impressions"]),
        "clicks": _pair(now["clicks"], then["clicks"]),
        "position": _pair(now["position"], then["position"]),
    }


def status_for(google: dict, bing: dict) -> str:
    """One label per term, from Google first, since that is where most of the searching is."""
    for name, engine in (("", google), (" (Bing)", bing)):
        impressions = engine["impressions"]["current"] or 0
        if impressions <= 0:
            continue
        if impressions < MIN_IMPRESSIONS_FOR_POSITION:
            return f"Barely showing{name}"
        position = engine["position"]["current"]
        if position is None:
            continue
        if position <= 3:
            return f"Top 3{name}"
        if position <= 10:
            return f"Page 1{name}"
        if position <= 20:
            return f"Page 2{name}"
        return f"Beyond page 2{name}"
    return "Not showing"


def _llm(db: Session, client: Client, month: str) -> dict[str, Any] | None:
    """The AI platforms' results for the month: every run done in it, pooled, against the month before.

    A weekly run is one snapshot of answers that move from day to day, so the month's figures pool all of its runs. With no run in
    the month, the latest run stands in (and is labelled as such), against the run before it.
    """
    from app.llm_visibility import report

    first, last = parse_month(month)
    start = datetime.combine(first, time.min, tzinfo=timezone.utc)
    done = db.query(LlmRun).filter(LlmRun.client_id == client.id, LlmRun.status == "completed")
    runs = report.month_runs(db, client, month)
    in_month = bool(runs)
    if runs:
        prev_runs = report.month_runs(db, client, previous_month(month))
        if not prev_runs:
            older = done.filter(LlmRun.started_at < start).order_by(LlmRun.started_at.desc()).first()
            prev_runs = [older] if older else []
    else:
        latest = done.order_by(LlmRun.started_at.desc()).first()
        if latest is None:
            return None
        runs = [latest]
        older = done.filter(LlmRun.started_at < latest.started_at).order_by(LlmRun.started_at.desc()).first()
        prev_runs = [older] if older else []
    rows = [r for run in runs for r in db.query(LlmResponse).filter(LlmResponse.run_id == run.id).all()]
    prev_rows = [r for run in prev_runs for r in db.query(LlmResponse).filter(LlmResponse.run_id == run.id).all()] if prev_runs else None
    return {
        "run_date": runs[-1].started_at.date().isoformat(),
        "run_dates": [r.started_at.date().isoformat() for r in runs],
        "runs": len(runs),
        "in_month": in_month,
        "previous_run_date": prev_runs[-1].started_at.date().isoformat() if prev_runs else None,
        "previous_runs": len(prev_runs),
        "summary": report.summary(rows, prev_rows),
        "platforms": report.platform_deltas(rows, prev_rows),
        "brand_check": report.brand_check(rows)["platforms"],
        "_rows": rows,
        "_prev": prev_rows,
    }


def _term_ai(prompt: str | None, rows: list[Any], prev: list[Any] | None) -> dict[str, Any] | None:
    """How the platforms answered one term's paired prompt: how many named or cited the brand, against the last run."""
    if not prompt:
        return None
    key = key_of(prompt)

    def tally(source: list[Any] | None) -> tuple[int, int, int] | None:
        if source is None:
            return None
        mine = [r for r in source if r.visibility_type != "Error" and key_of(r.query_text) == key]
        if not mine:
            return None
        return len(mine), sum(bool(r.url_cited) for r in mine), sum(bool(r.brand_mentioned) for r in mine)

    now, then = tally(rows), tally(prev)
    if now is None:
        return None
    # One run gives one answer per platform. Pooled runs give several: a platform counts as having cited or named the brand when it did so in at least half of them.
    per_platform: dict[str, list[Any]] = defaultdict(list)
    for r in rows:
        if r.visibility_type != "Error" and key_of(r.query_text) == key:
            per_platform[r.platform].append(r)
    by_platform = {
        platform: {"cited": sum(bool(r.url_cited) for r in got) * 2 >= len(got), "named": sum(bool(r.brand_mentioned) for r in got) * 2 >= len(got)}
        for platform, got in per_platform.items()
    }
    return {
        "by_platform": by_platform,
        "platforms": now[0],
        "cited": now[1],
        "mentioned": now[2],
        "previous_cited": then[1] if then else None,
        "previous_mentioned": then[2] if then else None,
    }


def build_visibility(db: Session, client: Client, month: str) -> dict | None:
    """The watchlist grouped by bucket, with Google and Bing for the month and the one before."""
    rows = (
        db.query(WatchlistKeyword, WatchlistBucket)
        .join(WatchlistBucket, WatchlistBucket.id == WatchlistKeyword.bucket_id)
        .filter(WatchlistKeyword.client_id == client.id)
        .order_by(WatchlistBucket.sort_order, WatchlistBucket.name, WatchlistKeyword.volume.desc().nulls_last())
        .all()
    )
    if not rows:
        return None

    first, last = parse_month(month)
    prev_first, prev_last = parse_month(previous_month(month))
    keys = sorted({key_of(k.keyword) for k, _ in rows})

    g_now, g_then = _google(db, client, keys, first, last), _google(db, client, keys, prev_first, prev_last)
    b_now, b_then = _bing(db, client, keys, first, last), _bing(db, client, keys, prev_first, prev_last)

    bing_range = db.query(func.min(FactBingQueryStat.week_start), func.max(FactBingQueryStat.week_start)).filter(
        FactBingQueryStat.client_id == client.id
    ).one()

    llm = _llm(db, client, month)
    llm_rows = llm["_rows"] if llm else []
    llm_prev = llm["_prev"] if llm else None

    buckets: dict[str, dict] = {}
    for keyword, bucket in rows:
        k = key_of(keyword.keyword)
        google, bing = _engine(g_now.get(k), g_then.get(k)), _engine(b_now.get(k), b_then.get(k))
        entry = buckets.setdefault(str(bucket.id), {"id": str(bucket.id), "name": bucket.name, "terms": []})
        entry["terms"].append(
            {
                "keyword": keyword.keyword,
                "volume": keyword.volume,
                "prompt": keyword.paired_ai_prompt,
                "google": google,
                "bing": bing,
                "status": status_for(google, bing),
                "ai": _term_ai(keyword.paired_ai_prompt, llm_rows, llm_prev),
            }
        )

    terms = [t for b in buckets.values() for t in b["terms"]]
    showing = [t for t in terms if (t["google"]["impressions"]["current"] or 0) > 0]
    page_one = [t for t in terms if t["status"].startswith(("Top 3", "Page 1"))]
    summary = {
        "terms": len(terms),
        "showing_in_google": len(showing),
        "on_page_one": len(page_one),
        "showing_in_bing": sum(1 for t in terms if (t["bing"]["impressions"]["current"] or 0) > 0),
        "google_impressions": sum(t["google"]["impressions"]["current"] or 0 for t in terms),
        "google_clicks": sum(t["google"]["clicks"]["current"] or 0 for t in terms),
        "prompts": sum(1 for t in terms if t["prompt"]),
    }
    return {
        "month": month,
        "buckets": list(buckets.values()),
        "summary": summary,
        "has_google_data": bool(g_now) or bool(g_then),
        "bing": {
            "has_data": bing_range[0] is not None,
            "first_week": bing_range[0].isoformat() if bing_range[0] else None,
            "last_week": bing_range[1].isoformat() if bing_range[1] else None,
            "note": "Bing reports weekly. A week counts toward the month it starts in.",
        },
        "ai_prompts": "The prompt shown is the one paired with the term; its answers come from the LLM visibility run.",
        "llm": ({k: v for k, v in llm.items() if not k.startswith("_")} if llm else None),
    }
