"""The monthly performance report's numbers, laid out the way a consultant writes the report: three outcomes, then one table per topic.

Every figure is this month against last month and against the same month last year, with a three-month run, so a reader sees direction as well as level.
A comparison that has no data (the site was not synced a year ago, a channel did not exist) is None and is said so on screen; nothing is estimated.
The figures come from the same synced Google Analytics, Search Console and SE Ranking facts as the rest of Organic IQ.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.visibility_candidates import add_months
from app.models.client import Client
from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscDaily
from app.models.seranking import FactSerRanking
from app.services import bi, monthly_review, review_scorecards

AI_NAMES = (("chatgpt", "ChatGPT"), ("openai", "ChatGPT"), ("gemini", "Gemini"), ("perplexity", "Perplexity"), ("copilot", "Copilot"), ("claude", "Claude"), ("anthropic", "Claude"))
RANK_ROWS = 15
LANDING_ROWS = 10


def _pct(now: float | None, then: float | None) -> float | None:
    return None if now is None or not then else round((now - then) / then * 100, 1)


def _month_bounds(month: str) -> tuple[date, date]:
    return monthly_review.parse_month(month)


def _shift(month: str, months: int) -> str:
    first, _ = _month_bounds(month)
    d = add_months(first, months)
    return f"{d.year:04d}-{d.month:02d}"


def _lead_events(db: Session, client: Client) -> dict[str, str]:
    """GA4 event name -> the name the team gave the key action."""
    return {d.event_name: d.conversion_name for d in db.query(ConversionDefinition).filter(ConversionDefinition.client_id == client.id, ConversionDefinition.active.is_(True), ConversionDefinition.conversion_type == "lead")}


def _sessions(db: Session, client: Client, month: str, channel: OrganicChannel | None = None) -> float | None:
    first, last = _month_bounds(month)
    q = db.query(func.sum(FactGa4Traffic.sessions)).filter(FactGa4Traffic.client_id == client.id, FactGa4Traffic.date >= first, FactGa4Traffic.date <= last)
    if channel is not None:
        q = q.filter(FactGa4Traffic.channel == channel)
    v = q.scalar()
    return float(v) if v else None


def _events(db: Session, client: Client, month: str, names: list[str], *, channel: OrganicChannel | None = None) -> dict[str, float]:
    if not names:
        return {}
    first, last = _month_bounds(month)
    q = db.query(FactGa4Event.event_name, func.coalesce(func.sum(FactGa4Event.event_count), 0)).filter(FactGa4Event.client_id == client.id, FactGa4Event.date >= first, FactGa4Event.date <= last, FactGa4Event.event_name.in_(names))
    if channel is not None:
        q = q.filter(FactGa4Event.channel == channel)
    return {n: float(c or 0) for n, c in q.group_by(FactGa4Event.event_name).all()}


def _key_actions(db: Session, client: Client, month: str, defs: dict[str, str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for event, n in _events(db, client, month, list(defs)).items():
        out[defs[event]] = out.get(defs[event], 0.0) + n
    return out


def _top10(db: Session, client: Client, month: str) -> int | None:
    """Tracked keywords in Google's top 10 on the last day the rank tracker checked in the month."""
    first, last = _month_bounds(month)
    day = db.query(func.max(FactSerRanking.date)).filter(FactSerRanking.client_id == client.id, FactSerRanking.date >= first, FactSerRanking.date <= last).scalar()
    if day is None:
        return None
    positions = [float(p or 0) for (p,) in db.query(FactSerRanking.position).filter(FactSerRanking.client_id == client.id, FactSerRanking.date == day)]
    return sum(1 for p in positions if 0 < p <= 10)


def _run(values: dict[str, float | None], months: list[str]) -> list[dict[str, Any]]:
    return [{"month": m, "value": values.get(m)} for m in months]


def _card(label: str, caption: str, value: float | None, prev: float | None, yoy: float | None, run: list[dict[str, Any]], *, unit: str = "", lower_is_better: bool = False) -> dict[str, Any]:
    return {
        "label": label, "caption": caption, "value": value, "unit": unit, "lower_is_better": lower_is_better,
        "vs_previous": {"value": prev, "change_pct": _pct(value, prev)}, "vs_last_year": {"value": yoy, "change_pct": _pct(value, yoy)}, "run": run,
    }


def _ai_label(source: str) -> str:
    low = (source or "").lower()
    for needle, name in AI_NAMES:
        if needle in low:
            return name
    return (source or "Other").strip() or "Other"


def _ai_assistants(db: Session, client: Client, month: str, names: list[str]) -> list[dict[str, Any]]:
    def visits(m: str) -> dict[str, float]:
        first, last = _month_bounds(m)
        rows = db.query(FactGa4Traffic.session_source, func.coalesce(func.sum(FactGa4Traffic.sessions), 0)).filter(FactGa4Traffic.client_id == client.id, FactGa4Traffic.date >= first, FactGa4Traffic.date <= last, FactGa4Traffic.channel == OrganicChannel.AI_REFERRAL).group_by(FactGa4Traffic.session_source).all()
        out: dict[str, float] = {}
        for src, n in rows:
            out[_ai_label(src)] = out.get(_ai_label(src), 0.0) + float(n or 0)
        return out

    def actions(m: str) -> dict[str, float]:
        first, last = _month_bounds(m)
        if not names:
            return {}
        rows = db.query(FactGa4Event.session_source, func.coalesce(func.sum(FactGa4Event.event_count), 0)).filter(FactGa4Event.client_id == client.id, FactGa4Event.date >= first, FactGa4Event.date <= last, FactGa4Event.channel == OrganicChannel.AI_REFERRAL, FactGa4Event.event_name.in_(names)).group_by(FactGa4Event.session_source).all()
        out: dict[str, float] = {}
        for src, n in rows:
            out[_ai_label(src)] = out.get(_ai_label(src), 0.0) + float(n or 0)
        return out

    now, then, acts = visits(month), visits(_shift(month, -1)), actions(month)
    rows = [{"label": k, "sessions": round(now.get(k, 0)), "previous": round(then.get(k, 0)), "change_pct": _pct(now.get(k, 0), then.get(k, 0)), "key_actions": round(acts[k]) if k in acts else None} for k in {*now, *then}]
    rows.sort(key=lambda r: (-r["sessions"], r["label"]))
    return rows


def _landing_pages(db: Session, client: Client, month: str, names: list[str]) -> list[dict[str, Any]]:
    first, last = _month_bounds(month)
    pfirst, plast = _month_bounds(_shift(month, -1))

    def sessions(a: date, b: date) -> dict[str, float]:
        rows = db.query(FactGa4Traffic.normalized_url, func.coalesce(func.sum(FactGa4Traffic.sessions), 0)).filter(FactGa4Traffic.client_id == client.id, FactGa4Traffic.date >= a, FactGa4Traffic.date <= b, FactGa4Traffic.channel == OrganicChannel.ORGANIC_SEARCH).group_by(FactGa4Traffic.normalized_url).all()
        return {u: float(n or 0) for u, n in rows}

    now, then = sessions(first, last), sessions(pfirst, plast)
    acts: dict[str, float] = {}
    if names:
        for u, n in db.query(FactGa4Event.normalized_url, func.coalesce(func.sum(FactGa4Event.event_count), 0)).filter(FactGa4Event.client_id == client.id, FactGa4Event.date >= first, FactGa4Event.date <= last, FactGa4Event.channel == OrganicChannel.ORGANIC_SEARCH, FactGa4Event.event_name.in_(names)).group_by(FactGa4Event.normalized_url):
            acts[u] = float(n or 0)
    top = sorted(now.items(), key=lambda kv: -kv[1])[:LANDING_ROWS]
    return [{"page": u, "sessions": round(n), "previous": round(then[u]) if u in then else None, "change_pct": _pct(n, then.get(u)), "key_actions": round(acts.get(u, 0))} for u, n in top]


def _rankings(db: Session, client: Client, month: str) -> dict[str, Any]:
    first, last = _month_bounds(month)
    moved = bi.keyword_movement(db, client, first, last)
    rows = [{"keyword": k["keyword"], "volume": k["volume"], "start": k["start"], "end": k["end"], "change": k["change"], "state": k["state"]} for k in moved["keywords"][:RANK_ROWS]]
    return {"checked_from": moved["from"], "checked_to": moved["to"], "coverage": moved["coverage"], "rows": rows}


def build(db: Session, client: Client, month: str) -> dict[str, Any]:
    first, last = _month_bounds(month)
    prev, year_ago = _shift(month, -1), _shift(month, -12)
    run_months = [_shift(month, -2), _shift(month, -1), month]
    defs = _lead_events(db, client)
    names = list(defs)

    # Conversions: key actions by type.
    cur_a, prev_a, ly_a = _key_actions(db, client, month, defs), _key_actions(db, client, prev, defs), _key_actions(db, client, year_ago, defs)
    total, total_prev, total_ly = sum(cur_a.values()), sum(prev_a.values()), sum(ly_a.values())
    rows = [{"label": k, "count": round(cur_a.get(k, 0)), "previous": round(prev_a.get(k, 0)), "change_pct": _pct(cur_a.get(k, 0), prev_a.get(k, 0)), "last_year": round(ly_a[k]) if k in ly_a else None} for k in {*cur_a, *prev_a}]
    rows.sort(key=lambda r: (-r["count"], r["label"]))
    totals = {m: sum(_key_actions(db, client, m, defs).values()) or None for m in run_months}
    conversions = _card("Conversions", "key actions completed", total or None, total_prev or None, total_ly or None, _run(totals, run_months)) if names else None

    # Traffic: organic search visits.
    org = {m: _sessions(db, client, m, OrganicChannel.ORGANIC_SEARCH) for m in run_months}
    traffic = _card("Traffic", "organic search visits", org[month], org[prev], _sessions(db, client, year_ago, OrganicChannel.ORGANIC_SEARCH), _run(org, run_months)) if org[month] or org[prev] else None

    # Visibility: tracked keywords in Google's top 10 (rank tracker).
    tops = {m: _top10(db, client, m) for m in run_months}
    rankings = _rankings(db, client, month)
    cov = rankings["coverage"] or {}
    visibility = None
    if tops[month] is not None:
        visibility = _card("Visibility", "tracked keywords in Google's top 10", float(tops[month]), float(tops[prev]) if tops[prev] is not None else None, float(_top10(db, client, year_ago)) if _top10(db, client, year_ago) is not None else None, _run({m: (float(v) if v is not None else None) for m, v in tops.items()}, run_months))
        visibility["facts"] = [f"{cov.get('tracked', 0)} keywords tracked"] if cov else []

    # Google clicks, site-wide, as supporting context.
    def gsc(m: str) -> float | None:
        a, b = _month_bounds(m)
        v = db.query(func.sum(FactGscDaily.clicks)).filter(FactGscDaily.client_id == client.id, FactGscDaily.date >= a, FactGscDaily.date <= b).scalar()
        return float(v) if v else None

    clicks = {"value": gsc(month), "vs_previous": _pct(gsc(month), gsc(prev)), "vs_last_year": _pct(gsc(month), gsc(year_ago))}

    mix = review_scorecards.traffic_mix(db, client, month)
    all_visits = sum(c["sessions"] for c in mix) or None
    channels = [{"key": c["key"], "label": c["label"], "sessions": c["sessions"], "share_pct": round(c["sessions"] / all_visits * 100, 1) if all_visits else None, "previous": c["previous"], "change_pct": c["change_pct"]} for c in mix]

    return {
        "month": month, "site": client.domain, "previous_month": prev, "last_year": year_ago, "period": [first.isoformat(), last.isoformat()],
        "outcomes": {"conversions": conversions, "visibility": visibility, "traffic": traffic},
        "google_clicks": clicks, "key_actions": {"rows": rows, "total": {"count": round(total), "previous": round(total_prev), "change_pct": _pct(total, total_prev)} if names else None, "has_definitions": bool(names)},
        "rankings": rankings, "channels": channels, "all_visits": all_visits, "landing_pages": _landing_pages(db, client, month, names),
        "ai_assistants": _ai_assistants(db, client, month, names),
        "sources": ["Google Analytics 4", "Search Console", "SE Ranking"],
    }
