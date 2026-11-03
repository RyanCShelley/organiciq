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


def keyword_movement(db: Session, client: Client, start: date, end: date) -> dict[str, Any]:
    """Each tracked keyword's position on the first and last tracked day of the range. A position of 0 means not ranking."""
    days = [d for (d,) in db.query(FactSerRanking.date).filter(FactSerRanking.client_id == client.id, FactSerRanking.date >= start, FactSerRanking.date <= end).distinct().order_by(FactSerRanking.date)]
    if not days:
        return {"from": None, "to": None, "keywords": []}
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
    for item in out:
        s, e = item["start"], item["end"]
        item["change"] = round(s - e, 1) if s is not None and e is not None else None  # positive: moved up
        item["state"] = "new" if s is None and e is not None else "lost" if s is not None and e is None else "up" if (item["change"] or 0) > 0.5 else "down" if (item["change"] or 0) < -0.5 else "steady"
    out.sort(key=lambda r: (r["start"] is None and r["end"] is None, -(r["volume"] or 0)))  # ranking ones first, then by searches
    return {"from": first.isoformat(), "to": last.isoformat(), "keywords": out[:KEYWORDS_SHOWN]}


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
