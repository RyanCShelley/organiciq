"""The LLM visibility reports, worked out from a run's responses and the run before it.

A port of llmviz's delta and view maths. Pure functions over rows with the `LlmResponse` attributes, so
they are tested without a database. Error rows are never counted.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.llm_visibility import LlmResponse, LlmRun

MONTH_ANSWER_CAP = 2000
VISIBLE = ("Cited + Mentioned", "Cited", "Mentioned")
CODES = {"Cited + Mentioned": "C+M", "Cited": "C", "Mentioned": "M"}


def _valid(rows: Iterable[Any]) -> list[Any]:
    """Answers that say something about discovery: not errors, and not prompts that already named the brand."""
    return [r for r in rows if r.visibility_type and r.visibility_type != "Error" and not getattr(r, "asked_by_name", False)]


def brand_check(rows: Iterable[Any]) -> dict[str, Any]:
    """Prompts that name the brand: does each platform cite the site? A mention here only repeats the question."""
    named = [r for r in rows if getattr(r, "asked_by_name", False)]
    per_platform: dict[str, dict[str, int]] = {}
    per_prompt: dict[str, dict[str, Any]] = {}
    for r in named:
        if r.visibility_type == "Error":
            continue
        p = per_platform.setdefault(r.platform, {"answers": 0, "site_cited": 0})
        p["answers"] += 1
        p["site_cited"] += bool(r.url_cited)
        q = per_prompt.setdefault(r.query_text, {"query": r.query_text, "topic_cluster": r.topic_cluster, "by_platform": {}})
        q["by_platform"][r.platform] = "Cited" if r.url_cited else "Not cited"
    return {
        "platforms": [{"platform": k, **v} for k, v in sorted(per_platform.items())],
        "prompts": sorted(per_prompt.values(), key=lambda q: (q["topic_cluster"] or "", q["query"])),
    }


def _pair(current: float, previous: float | None, scale: float = 1.0) -> dict[str, float | None]:
    """`scale` brings a previous count to the current side's number of runs (a month with 1 run so far against one with 4), so counts compare like with like."""
    if previous is not None and scale != 1.0:
        previous = round(previous * scale, 1)
    return {"current": current, "previous": previous, "delta": None if previous is None else round(current - previous, 4)}


def _score(visibility: str | None) -> int:
    return 2 if visibility == "Cited + Mentioned" else 1 if visibility in ("Cited", "Mentioned") else 0


def _platform_bucket(rows: list[Any]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for r in _valid(rows):
        b = out.setdefault(r.platform, {"n": 0, "visible": 0, "mentions": 0, "citations": 0, "rank_sum": 0, "rank_n": 0, "cm": 0, "c": 0, "m": 0, "nv": 0})
        b["n"] += 1
        b["visible"] += r.visibility_type in VISIBLE
        b["mentions"] += bool(r.brand_mentioned)
        b["citations"] += bool(r.url_cited)
        b["cm"] += r.visibility_type == "Cited + Mentioned"
        b["c"] += r.visibility_type == "Cited"
        b["m"] += r.visibility_type == "Mentioned"
        b["nv"] += r.visibility_type == "Not visible"
        if r.brand_rank and r.brand_rank > 0:
            b["rank_sum"] += r.brand_rank
            b["rank_n"] += 1
    return out


def _rate(b: dict[str, float]) -> float:
    return round(b["visible"] / b["n"], 4) if b["n"] else 0.0


def _rank(b: dict[str, float]) -> float | None:
    return round(b["rank_sum"] / b["rank_n"], 2) if b["rank_n"] else None


def platform_deltas(current: list[Any], previous: list[Any] | None, prev_scale: float = 1.0) -> list[dict[str, Any]]:
    cur = _platform_bucket(current)
    prev = _platform_bucket(previous) if previous is not None else None
    out = []
    for platform in sorted(cur):
        c, p = cur[platform], (prev or {}).get(platform)
        out.append(
            {
                "platform": platform,
                "queries_checked": int(c["n"]),
                "by_type": {"cited_mentioned": int(c["cm"]), "cited": int(c["c"]), "mentioned": int(c["m"]), "not_visible": int(c["nv"])},
                "mentions": _pair(c["mentions"], p["mentions"] if p else (0 if prev is not None else None), prev_scale),
                "citations": _pair(c["citations"], p["citations"] if p else (0 if prev is not None else None), prev_scale),
                "visibility_rate": _pair(_rate(c), _rate(p) if p else (0.0 if prev is not None else None)),
                "avg_brand_rank": {"current": _rank(c), "previous": _rank(p) if p else None},
            }
        )
    return out


def _sov_bucket(rows: list[Any], brand: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in _valid(rows):
        cluster = r.topic_cluster or "Uncategorized"
        b = out.setdefault(cluster, {"total": 0, "brands": {brand: {"count": 0, "self": True}}})
        b["total"] += 1
        names = ([brand] if r.brand_mentioned else []) + list(r.competitors_mentioned or [])
        for name in names:
            entry = b["brands"].setdefault(name, {"count": 0, "self": name == brand and bool(r.brand_mentioned)})
            entry["count"] += 1
    return out


def share_of_voice(current: list[Any], previous: list[Any] | None, brand: str, prev_scale: float = 1.0) -> list[dict[str, Any]]:
    cur = _sov_bucket(current, brand)
    prev = _sov_bucket(previous, brand) if previous is not None else None
    out = []
    for cluster, bucket in cur.items():
        pbucket = prev.get(cluster) if prev is not None else None
        for name, info in bucket["brands"].items():
            share = round(info["count"] / bucket["total"], 4) if bucket["total"] else 0.0
            pinfo = pbucket["brands"].get(name) if pbucket else None
            prev_share = (round(pinfo["count"] / pbucket["total"], 4) if pinfo and pbucket["total"] else 0.0) if pbucket else None
            out.append(
                {
                    "topic_cluster": cluster,
                    "brand": name,
                    "is_self": name == brand,
                    "mentions": _pair(info["count"], (pinfo["count"] if pinfo else 0) if pbucket else None, prev_scale),
                    "share": _pair(share, prev_share),
                    "responses": bucket["total"],
                }
            )
    out.sort(key=lambda r: (r["topic_cluster"], -r["mentions"]["current"]))
    return out


def _query_bucket(rows: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in _valid(rows):
        b = out.setdefault(r.query_text, {"query": r.query_text, "cluster": r.topic_cluster, "keyword": r.keyword, "score": 0, "max": 0, "platforms": {}, "ranks": [], "competitors": Counter()})
        b["score"] += _score(r.visibility_type)
        b["max"] += 2
        b["platforms"][r.platform] = CODES.get(r.visibility_type, "—")
        if r.brand_rank and r.brand_rank > 0:
            b["ranks"].append(r.brand_rank)
        b["competitors"].update(r.competitors_mentioned or [])
    return out


def query_summary(current: list[Any], previous: list[Any] | None) -> list[dict[str, Any]]:
    """One row per prompt: how each platform did, its score, and how that moved since the last run."""
    cur = _query_bucket(current)
    prev = _query_bucket(previous) if previous is not None else None
    rows = []
    for text, b in cur.items():
        before = prev.get(text)["score"] if prev is not None and text in prev else None
        rows.append(
            {
                "query": text,
                "keyword": b["keyword"],
                "topic_cluster": b["cluster"],
                "by_platform": b["platforms"],
                "score": b["score"],
                "max_score": b["max"],
                "previous_score": before,
                "change": None if before is None else b["score"] - before,
                "avg_brand_rank": round(sum(b["ranks"]) / len(b["ranks"]), 1) if b["ranks"] else None,
                "top_competitors": [{"name": n, "count": c} for n, c in b["competitors"].most_common(3)],
            }
        )
    rows.sort(key=lambda r: (r["topic_cluster"] or "", -r["score"], r["query"]))
    return rows


def movers(rows: list[dict[str, Any]], limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    improved = sorted((r for r in rows if (r["change"] or 0) > 0), key=lambda r: -r["change"])
    declined = sorted((r for r in rows if (r["change"] or 0) < 0), key=lambda r: r["change"])
    return {"improved": improved[:limit], "declined": declined[:limit]}


def summary(current: list[Any], previous: list[Any] | None, prev_scale: float = 1.0) -> dict[str, Any]:
    def tally(rows: list[Any]) -> tuple[int, int, int, int]:
        valid = _valid(rows)
        return (
            sum(bool(r.brand_mentioned) for r in valid),
            sum(bool(r.url_cited) for r in valid),
            sum(r.visibility_type in VISIBLE for r in valid),
            len(valid),
        )

    m, c, v, n = tally(current)
    pm = pc = pv = pn = None
    if previous is not None:
        pm, pc, pv, pn = tally(previous)
    rate = round(v / n, 4) if n else 0.0
    prev_rate = round(pv / pn, 4) if pn else (0.0 if previous is not None else None)
    return {
        "mentions": _pair(m, pm, prev_scale),
        "citations": _pair(c, pc, prev_scale),
        "visibility_rate": _pair(rate, prev_rate),
        "responses": n,
    }


def _rows(db: Session, run_id: UUID) -> list[LlmResponse]:
    return db.query(LlmResponse).filter(LlmResponse.run_id == run_id).all()


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    year, mon = int(month[:4]), int(month[5:7])
    start = datetime(year, mon, 1, tzinfo=timezone.utc)
    end = datetime(year + (mon == 12), mon % 12 + 1, 1, tzinfo=timezone.utc)
    return start, end


def _prev_month(month: str) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    return f"{year - (mon == 1):04d}-{(mon - 2) % 12 + 1:02d}"


def month_runs(db: Session, client: Client, month: str) -> list[LlmRun]:
    """The completed runs that started in a month (UTC), oldest first."""
    start, end = _month_bounds(month)
    return (
        db.query(LlmRun)
        .filter(LlmRun.client_id == client.id, LlmRun.status == "completed", LlmRun.started_at >= start, LlmRun.started_at < end)
        .order_by(LlmRun.started_at)
        .all()
    )


def run_months(db: Session, client: Client) -> list[str]:
    """Months with at least one completed run, newest first."""
    seen = {r.started_at.strftime("%Y-%m") for r in db.query(LlmRun).filter(LlmRun.client_id == client.id, LlmRun.status == "completed")}
    return sorted(seen, reverse=True)


def month_share_of_voice(db: Session, client: Client, brand: str, month: str) -> dict[str, Any]:
    """Share of voice over every run in a month, pooled: each brand's answers named over all the month's answers in a topic.

    One run is a snapshot; a model's answers move from day to day, so the month's pooled figure is steadier. Each row also carries
    its share in each run, so how far it moved within the month is visible.
    """
    runs = month_runs(db, client, month)
    per_run = [_rows(db, r.id) for r in runs]
    pooled = [row for rows in per_run for row in rows]
    prev_runs = month_runs(db, client, _prev_month(month))
    prev_rows = [row for r in prev_runs for row in _rows(db, r.id)] if prev_runs else None
    rows = share_of_voice(pooled, prev_rows, brand, len(runs) / len(prev_runs) if prev_runs and runs else 1.0)
    buckets = [_sov_bucket(rows_, brand) for rows_ in per_run]
    for r in rows:
        shares: list[float | None] = []
        for b in buckets:
            bucket = b.get(r["topic_cluster"])
            info = bucket["brands"].get(r["brand"]) if bucket else None
            shares.append(round(info["count"] / bucket["total"], 4) if bucket and info is not None and bucket["total"] else (0.0 if bucket else None))
        r["by_run"] = shares
    return {
        "month": month, "months": run_months(db, client), "brand": brand,
        "runs": [{"id": str(r.id), "started_at": r.started_at.isoformat()} for r in runs],
        "previous_runs": len(prev_runs), "answers": len(_valid(pooled)), "share_of_voice": rows,
    }


def month_responses(db: Session, client: Client, month: str) -> dict[str, Any]:
    """Every answer from a month's runs, newest run first, each marked with its run's date: {answers, total}. Capped so the pane stays light; `total` says what the cap left out."""
    out: list[dict[str, Any]] = []
    for run in reversed(month_runs(db, client, month)):
        for row in run_responses(db, run):
            out.append({**row, "run_started_at": run.started_at.isoformat(), "run_id": str(run.id)})
    return {"answers": out[:MONTH_ANSWER_CAP], "total": len(out)}


def _previous_run(db: Session, run: LlmRun) -> LlmRun | None:
    return (
        db.query(LlmRun)
        .filter(LlmRun.client_id == run.client_id, LlmRun.status == "completed", LlmRun.started_at < run.started_at)
        .order_by(LlmRun.started_at.desc())
        .first()
    )


def _run_out(run: LlmRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "status": run.status,
        "platforms": list(run.platforms or []),
        "total_calls": run.total_calls,
        "total_errors": run.total_errors,
        "estimated_cost_usd": float(run.estimated_cost_usd) if run.estimated_cost_usd is not None else None,
        "triggered_by": run.triggered_by,
        "error": run.error,
    }


def overview(db: Session, client: Client, brand: str, run_id: UUID | None = None) -> dict[str, Any]:
    """The home of LLM visibility: the chosen (default latest) run against the one before it, plus the trend."""
    runs = (
        db.query(LlmRun)
        .filter(LlmRun.client_id == client.id, LlmRun.status == "completed")
        .order_by(LlmRun.started_at.desc())
        .limit(12)
        .all()
    )
    running = db.query(LlmRun).filter(LlmRun.client_id == client.id, LlmRun.status == "running").order_by(LlmRun.started_at.desc()).first()
    base: dict[str, Any] = {"brand": brand, "runs": [_run_out(r) for r in runs], "running": _run_out(running) if running else None}
    run = next((r for r in runs if r.id == run_id), None) if run_id else (runs[0] if runs else None)
    if run is None:
        return {**base, "run": None}
    previous = _previous_run(db, run)
    cur_rows = _rows(db, run.id)
    prev_rows = _rows(db, previous.id) if previous else None
    queries = query_summary(cur_rows, prev_rows)

    trend = []
    for r in reversed(runs):
        s = summary(_rows(db, r.id), None)
        trend.append({"run_id": str(r.id), "started_at": r.started_at.isoformat(), "visibility_rate": s["visibility_rate"]["current"], "mentions": s["mentions"]["current"], "citations": s["citations"]["current"]})

    errors = Counter((r.platform, r.error) for r in cur_rows if r.visibility_type == "Error")
    return {
        **base,
        "run": _run_out(run),
        "previous_run": _run_out(previous) if previous else None,
        "summary": summary(cur_rows, prev_rows),
        "platforms": platform_deltas(cur_rows, prev_rows),
        "share_of_voice": share_of_voice(cur_rows, prev_rows, brand),
        "queries": queries,
        "brand_check": brand_check(cur_rows),
        "movers": movers(queries),
        "trend": trend,
        "errors": [{"platform": p, "message": m, "count": n} for (p, m), n in errors.most_common(5)],
        "other_brands": [{"name": n, "count": c} for n, c in Counter(b for r in _valid(cur_rows) for b in (r.other_brands_mentioned or [])).most_common(10)],
    }


def run_responses(db: Session, run: LlmRun) -> list[dict[str, Any]]:
    """The full run: every prompt on every platform, with the answer as given."""
    rows = sorted(_rows(db, run.id), key=lambda r: (r.topic_cluster or "", r.query_text, r.platform))
    return [
        {
            "query": r.query_text,
            "keyword": r.keyword,
            "topic_cluster": r.topic_cluster,
            "platform": r.platform,
            "visibility": r.visibility_type,
            "asked_by_name": bool(r.asked_by_name),
            "brand_mentioned": bool(r.brand_mentioned),
            "url_cited": bool(r.url_cited),
            "cited_urls": list(r.cited_urls or []),
            "position": r.position,
            "brand_rank": r.brand_rank or None,
            "competitors": list(r.competitors_mentioned or []),
            "other_brands": list(r.other_brands_mentioned or []),
            "answer": r.full_response,
            "error": r.error,
        }
        for r in rows
    ]
