"""Google's ranking updates: read from its public Search Status Dashboard, kept, and listed for a date range."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.google_update import GoogleSearchUpdate

logger = logging.getLogger("organiciq.google_updates")

FEED = "https://status.search.google.com/incidents.json"
REFRESH_HOURS = 24
BASE = "https://status.search.google.com/"


def _day(text: str | None) -> date | None:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date() if text else None
    except ValueError:
        return None


def parse(feed: Any) -> list[dict[str, Any]]:
    """Ranking incidents only: a core or spam update is the kind that moves positions."""
    out = []
    for item in feed if isinstance(feed, list) else []:
        if (item.get("service_name") or "").lower() != "ranking":
            continue
        begin = _day(item.get("begin"))
        if begin is None or not item.get("id"):
            continue
        recent = item.get("most_recent_update") or {}
        out.append(
            {
                "id": str(item["id"])[:64], "title": str(item.get("external_desc") or "Ranking update")[:300], "begin": begin, "end": _day(item.get("end")),
                "summary": (recent.get("text") or "")[:600] or None, "url": BASE + str(item["uri"]) if item.get("uri") else None,
            }
        )
    return out


def refresh(db: Session, *, now: datetime | None = None) -> int:
    """Fetch the feed if what is held is over a day old. A failure keeps what is there."""
    now = now or datetime.now(timezone.utc)
    newest = db.query(GoogleSearchUpdate.fetched_at).order_by(GoogleSearchUpdate.fetched_at.desc()).limit(1).scalar()
    if newest is not None and now - newest < timedelta(hours=REFRESH_HOURS):
        return 0
    try:
        response = httpx.get(FEED, timeout=15.0)
        response.raise_for_status()
        rows = parse(response.json())
    except Exception as exc:  # noqa: BLE001 - the overlay is a nicety; the report works without it
        logger.warning("Google updates feed not read: %s", exc)
        return 0
    for row in rows:
        existing = db.get(GoogleSearchUpdate, row["id"])
        if existing is None:
            db.add(GoogleSearchUpdate(**row, fetched_at=now))
        else:
            for k, v in row.items():
                setattr(existing, k, v)
            existing.fetched_at = now
    db.commit()
    return len(rows)


def between(db: Session, start: date, end: date) -> list[dict[str, Any]]:
    rows = (
        db.query(GoogleSearchUpdate)
        .filter(GoogleSearchUpdate.begin <= end, (GoogleSearchUpdate.end.is_(None)) | (GoogleSearchUpdate.end >= start))
        .order_by(GoogleSearchUpdate.begin)
        .all()
    )
    return [{"id": r.id, "title": r.title, "begin": r.begin.isoformat(), "end": r.end.isoformat() if r.end else None, "summary": r.summary, "url": r.url} for r in rows]
