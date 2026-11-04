"""Business Intelligence: the drill-downs behind the monthly review's numbers, for any date range.

Every figure comes from a stored table and says which. A figure the data cannot give is None (for example, time on
site before Google Analytics has been pulled again), never a guess.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.annotation import Annotation, AnnotationType
from app.models.client import Client
from app.models.config import ConversionDefinition
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.seranking import FactSerRanking
from app.services.dashboard import CHANNEL_LABELS

PAGES_SHOWN = 25
KEYWORDS_SHOWN = 40


def _f(value: Decimal | float | int | None) -> float:
    return float(value or 0)


def _rate(part: float, whole: float) -> float | None:
    return round(part / whole * 100, 2) if whole > 0 else None


def key_events(db: Session, client: Client) -> list[dict[str, str]]:
    """The events the team chose as conversions, with what each is called."""
    rows = (
        db.query(ConversionDefinition.event_name, ConversionDefinition.conversion_name, ConversionDefinition.conversion_type)
        .filter(ConversionDefinition.client_id == client.id, ConversionDefinition.active.is_(True))
        .order_by(ConversionDefinition.is_primary.desc(), ConversionDefinition.conversion_name)
        .all()
    )
    return [{"event": e, "name": n, "type": t} for e, n, t in rows]


def _traffic_by(db: Session, client: Client, start: date, end: date, column, extra=()) -> dict[Any, dict[str, float]]:
    rows = (
        db.query(
            column,
            func.sum(FactGa4Traffic.sessions),
            func.sum(FactGa4Traffic.engaged_sessions),
            func.sum(FactGa4Traffic.engagement_seconds),
            func.sum(func.coalesce(FactGa4Traffic.sessions, 0)).filter(FactGa4Traffic.engagement_seconds.isnot(None)),
        )
        .filter(FactGa4Traffic.client_id == client.id, FactGa4Traffic.date >= start, FactGa4Traffic.date <= end, *extra)
        .group_by(column)
        .all()
    )
    return {
        key: {"sessions": _f(s), "engaged": _f(e), "seconds": _f(sec), "timed_sessions": _f(timed)}
        for key, s, e, sec, timed in rows
    }


def _events_by(db: Session, client: Client, start: date, end: date, column, events: list[str], extra=()) -> dict[Any, float]:
    if not events:
        return {}
    rows = (
        db.query(column, func.sum(FactGa4Event.event_count))
        .filter(
            FactGa4Event.client_id == client.id, FactGa4Event.date >= start, FactGa4Event.date <= end,
            FactGa4Event.event_name.in_(events), *extra,
        )
        .group_by(column)
        .all()
    )
    return {key: _f(n) for key, n in rows}


def _avg_seconds(t: dict[str, float]) -> float | None:
    """Average engaged time per session, over the sessions whose time was pulled."""
    return round(t["seconds"] / t["timed_sessions"], 1) if t["timed_sessions"] > 0 else None


def totals(db: Session, client: Client, start: date, end: date, events: list[str]) -> dict[str, Any]:
    """The whole site for a range: visits, engaged visits, time, and key actions."""
    row = (
        db.query(
            func.sum(FactGa4Traffic.sessions), func.sum(FactGa4Traffic.engaged_sessions), func.sum(FactGa4Traffic.engagement_seconds),
            func.sum(FactGa4Traffic.sessions).filter(FactGa4Traffic.engagement_seconds.isnot(None)),
        )
        .filter(FactGa4Traffic.client_id == client.id, FactGa4Traffic.date >= start, FactGa4Traffic.date <= end)
        .one()
    )
    sessions, engaged, seconds, timed = (_f(x) for x in row)
    conversions = sum(_events_by(db, client, start, end, FactGa4Event.client_id, events).values())
    return {
        "sessions": round(sessions), "engaged": round(engaged), "engagement_rate": _rate(engaged, sessions),
        "avg_seconds": round(seconds / timed, 1) if timed > 0 else None,
        "conversions": round(conversions), "conversion_rate": _rate(conversions, sessions),
    }


def daily(db: Session, client: Client, start: date, end: date, events: list[str]) -> list[dict[str, Any]]:
    """One row per day of the range, with the same day-of-range of the previous period beside it, for the over-time charts."""
    ps, _pe = previous_range(start, end)
    days = (end - start).days + 1
    span_start, span_end = ps, end

    visits = {d: (_f(s), _f(e)) for d, s, e in db.query(FactGa4Traffic.date, func.sum(FactGa4Traffic.sessions), func.sum(FactGa4Traffic.engaged_sessions)).filter(
        FactGa4Traffic.client_id == client.id, FactGa4Traffic.date >= span_start, FactGa4Traffic.date <= span_end).group_by(FactGa4Traffic.date)}
    actions = _events_by(db, client, span_start, span_end, FactGa4Event.date, events)
    out = []
    for i in range(days):
        d, p = start + timedelta(days=i), ps + timedelta(days=i)
        out.append(
            {
                "date": d.isoformat(),
                "sessions": round(visits.get(d, (0, 0))[0]), "sessions_before": round(visits.get(p, (0, 0))[0]),
                "engaged": round(visits.get(d, (0, 0))[1]),
                "conversions": round(actions.get(d, 0.0)), "conversions_before": round(actions.get(p, 0.0)),
            }
        )
    return out


def _latest_runs(db: Session, client: Client, end: date):
    """The latest finished LLM run up to the end of the range, and the one before it."""
    from app.models.llm_visibility import LlmRun

    runs = (
        db.query(LlmRun)
        .filter(LlmRun.client_id == client.id, LlmRun.status == "completed", func.date(LlmRun.started_at) <= end)
        .order_by(LlmRun.started_at.desc())
        .limit(2)
        .all()
    )
    return runs


def ai_mentions(db: Session, client: Client, end: date) -> dict[str, Any] | None:
    """How often the AI platforms name or cite the brand: the latest finished run up to the end of the range, against the run before it."""
    from app.llm_visibility.report import _valid
    from app.models.llm_visibility import LlmResponse

    runs = _latest_runs(db, client, end)
    if not runs:
        return None

    def rates(run) -> dict[str, Any]:
        rows = _valid(db.query(LlmResponse).filter(LlmResponse.run_id == run.id, LlmResponse.client_id == client.id).all())
        by: dict[str, dict[str, int]] = {}
        for r in rows:
            p = by.setdefault(r.platform, {"checks": 0, "mentioned": 0, "cited": 0})
            p["checks"] += 1
            p["mentioned"] += bool(r.brand_mentioned)
            p["cited"] += bool(r.url_cited)
        n = len(rows)
        return {
            "date": run.started_at.date().isoformat(), "checks": n,
            "mention_rate": _rate(sum(p["mentioned"] for p in by.values()), n), "cited_rate": _rate(sum(p["cited"] for p in by.values()), n),
            "platforms": [{"platform": k, **v} for k, v in sorted(by.items())],
        }

    now = rates(runs[0])
    before = rates(runs[1]) if len(runs) > 1 else None
    return {**now, "mention_rate_before": before and before["mention_rate"], "cited_rate_before": before and before["cited_rate"], "date_before": before and before["date"]}


def previous_range(start: date, end: date) -> tuple[date, date]:
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def channels(db: Session, client: Client, start: date, end: date, events: list[str]) -> list[dict[str, Any]]:
    """Each channel's visits, engagement, time and conversions, with the previous period's visits and conversions beside them."""
    ps, pe = previous_range(start, end)
    now = _traffic_by(db, client, start, end, FactGa4Traffic.channel)
    before = _traffic_by(db, client, ps, pe, FactGa4Traffic.channel)
    conv = _events_by(db, client, start, end, FactGa4Event.channel, events)
    conv_before = _events_by(db, client, ps, pe, FactGa4Event.channel, events)
    out = []
    for channel, t in now.items():
        c = conv.get(channel, 0.0)
        out.append(
            {
                "channel": channel.value,
                "label": CHANNEL_LABELS.get(channel, channel.value),
                "sessions": round(t["sessions"]),
                "sessions_before": round(before.get(channel, {}).get("sessions", 0)),
                "engagement_rate": _rate(t["engaged"], t["sessions"]),
                "avg_seconds": _avg_seconds(t),
                "conversions": round(c),
                "conversions_before": round(conv_before.get(channel, 0.0)),
                "conversion_rate": _rate(c, t["sessions"]),
            }
        )
    out.sort(key=lambda r: -r["sessions"])
    return out


def landing_pages(db: Session, client: Client, start: date, end: date, events: list[str], channel: str | None = None) -> list[dict[str, Any]]:
    """The busiest landing pages, optionally for one channel: visits, engagement, time on the page and key actions."""
    from app.models.config import OrganicChannel

    extra_t, extra_e = [], []
    if channel:
        chosen = OrganicChannel(channel)
        extra_t, extra_e = [FactGa4Traffic.channel == chosen], [FactGa4Event.channel == chosen]
    now = _traffic_by(db, client, start, end, FactGa4Traffic.normalized_url, extra_t)
    conv = _events_by(db, client, start, end, FactGa4Event.normalized_url, events, extra_e)
    out = []
    for url, t in sorted(now.items(), key=lambda kv: -kv[1]["sessions"])[:PAGES_SHOWN]:
        c = conv.get(url, 0.0)
        out.append(
            {
                "url": url,
                "sessions": round(t["sessions"]),
                "engagement_rate": _rate(t["engaged"], t["sessions"]),
                "avg_seconds": _avg_seconds(t),
                "conversions": round(c),
                "conversion_rate": _rate(c, t["sessions"]),
            }
        )
    return out


def _coverage(positions: list[float | None]) -> dict[str, int]:
    """How many tracked keywords sit in each band of the results. Not ranking counts as outside the top 100."""
    bands = {"top3": 0, "top10": 0, "top20": 0, "top100": 0, "outside": 0}
    for p in positions:
        key = "outside" if p is None else "top3" if p <= 3 else "top10" if p <= 10 else "top20" if p <= 20 else "top100" if p <= 100 else "outside"
        bands[key] += 1
    return bands


def keyword_movement(db: Session, client: Client, start: date, end: date) -> dict[str, Any]:
    """Each tracked keyword's position on the first and last tracked day of the range. A position of 0 means not ranking."""
    days = [d for (d,) in db.query(FactSerRanking.date).filter(FactSerRanking.client_id == client.id, FactSerRanking.date >= start, FactSerRanking.date <= end).distinct().order_by(FactSerRanking.date)]
    if not days:
        return {"from": None, "to": None, "coverage": None, "keywords": []}
    first, last = days[0], days[-1]
    rows = (
        db.query(FactSerRanking.keyword, FactSerRanking.date, FactSerRanking.position, FactSerRanking.volume, FactSerRanking.ranking_url)
        .filter(FactSerRanking.client_id == client.id, FactSerRanking.date.in_([first, last]))
        .all()
    )
    by: dict[str, dict[str, Any]] = {}
    for keyword, day, position, volume, url in rows:
        item = by.setdefault(keyword, {"keyword": keyword, "start": None, "end": None, "volume": None, "url": None})
        pos = _f(position) or None  # 0 or missing: not ranking
        if day == first:
            item["start"] = pos
        if day == last:
            item["end"], item["url"] = pos, url or None
            item["volume"] = _f(volume) if volume is not None else None
    out = list(by.values())
    coverage = {"start": _coverage([k["start"] for k in out]), "end": _coverage([k["end"] for k in out]), "tracked": len(out)}
    for item in out:
        s, e = item["start"], item["end"]
        item["change"] = round(s - e, 1) if s is not None and e is not None else None  # positive: moved up
        item["state"] = "new" if s is None and e is not None else "lost" if s is not None and e is None else "up" if (item["change"] or 0) > 0.5 else "down" if (item["change"] or 0) < -0.5 else "steady"
    out.sort(key=lambda r: (r["start"] is None and r["end"] is None, -(r["volume"] or 0)))  # ranking ones first, then by searches
    shown = out[:KEYWORDS_SHOWN]
    _attach_prompts(db, client, end, shown)
    return {"from": first.isoformat(), "to": last.isoformat(), "coverage": coverage, "keywords": shown}


def _attach_prompts(db: Session, client: Client, end: date, items: list[dict[str, Any]]) -> None:
    """Each keyword's watchlist volume and the AI prompt paired with it, and how the AI platforms answered that prompt in the
    latest run (named or cited the brand), against the run before."""
    from app.models.llm_visibility import LlmResponse
    from app.models.watchlist import WatchlistKeyword
    from app.services.review_visibility import _term_ai, key_of

    watch = {key_of(k): (v, p) for k, v, p in db.query(WatchlistKeyword.keyword, WatchlistKeyword.volume, WatchlistKeyword.paired_ai_prompt).filter(WatchlistKeyword.client_id == client.id)}
    runs = _latest_runs(db, client, end)
    rows = db.query(LlmResponse).filter(LlmResponse.run_id == runs[0].id, LlmResponse.client_id == client.id).all() if runs else []
    prev = db.query(LlmResponse).filter(LlmResponse.run_id == runs[1].id, LlmResponse.client_id == client.id).all() if len(runs) > 1 else None
    for item in items:
        volume, prompt = watch.get(key_of(item["keyword"]), (None, None))
        if item["volume"] is None and volume is not None:
            item["volume"] = float(volume)
        item["prompt"] = prompt
        item["ai"] = _term_ai(prompt, rows, prev)
        item["in_watchlist"] = key_of(item["keyword"]) in watch


def change_log(db: Session, client: Client, start: date, end: date) -> list[dict[str, Any]]:
    rows = (
        db.query(Annotation)
        .filter(Annotation.client_id == client.id, Annotation.date >= start, Annotation.date <= end)
        .order_by(Annotation.date.desc(), Annotation.created_at.desc())
        .all()
    )
    return [
        {"id": str(a.id), "date": a.date.isoformat(), "type": a.annotation_type.value, "description": a.description, "page": a.page_url, "from_task": a.engine_uid is not None}
        for a in rows
    ]


def build(db: Session, client: Client, start: date, end: date, channel: str | None = None) -> dict[str, Any]:
    events = key_events(db, client)
    names = [e["event"] for e in events]
    has_time = db.query(FactGa4Traffic.id).filter(FactGa4Traffic.client_id == client.id, FactGa4Traffic.date >= start, FactGa4Traffic.date <= end, FactGa4Traffic.engagement_seconds.isnot(None)).first() is not None
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "key_events": events,
        "has_engagement_time": has_time,
        "totals": totals(db, client, start, end, names),
        "totals_before": totals(db, client, *previous_range(start, end), names),
        "daily": daily(db, client, start, end, names),
        "ai": ai_mentions(db, client, end),
        "channels": channels(db, client, start, end, names),
        "pages": landing_pages(db, client, start, end, names, channel),
        "keywords": keyword_movement(db, client, start, end),
        "changes": change_log(db, client, start, end),
    }


def add_note(db: Session, client: Client, day: date, text: str, page: str | None = None) -> Annotation:
    note = Annotation(client_id=client.id, date=day, annotation_type=AnnotationType.MANUAL_NOTE, description=text.strip(), page_url=(page or None), baseline_metrics_json={})
    db.add(note)
    db.commit()
    return note
