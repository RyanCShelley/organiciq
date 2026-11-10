"""The LLM tracker's answers, read the way the rest of the app reads AI visibility.

One source: the tracker's own runs. The Decision Engine's AI rule (V5), the dated readings that measure a decision, the
watchlist's prompts, the dashboard's AI figures and the results screen all read from here, so what is shown is what is scored.

A prompt that already names the brand proves nothing by mentioning it, and an errored call says nothing, so both are left out
of every share (the same rule the LLM visibility screen uses).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.llm_visibility import report as llm_report
from app.models.llm_visibility import LlmResponse, LlmRun

SOURCE = "LLM tracker"


def _end_of(day: date) -> datetime:
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone.utc)


def _start_of(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _runs(db: Session, client_id: UUID, first: date | None, last: date) -> list[LlmRun]:
    q = db.query(LlmRun).filter(LlmRun.client_id == client_id, LlmRun.status == "completed", LlmRun.started_at < _end_of(last))
    if first is not None:
        q = q.filter(LlmRun.started_at >= _start_of(first))
    return q.order_by(LlmRun.started_at.desc()).all()


def _responses(db: Session, run_ids: list[UUID]) -> list[LlmResponse]:
    return db.query(LlmResponse).filter(LlmResponse.run_id.in_(run_ids)).all() if run_ids else []


def _shares(rows: list[Any]) -> dict[str, Any] | None:
    valid = llm_report._valid(rows)
    if not valid:
        return None
    seen = sum(1 for r in valid if r.visibility_type in llm_report.VISIBLE)
    cited = sum(1 for r in valid if r.url_cited)
    return {
        "mention_pct": round(seen / len(valid) * 100, 1),
        "cited_pct": round(cited / len(valid) * 100, 1),
        "answers": len(valid),
        "prompts": len({r.query_text for r in valid}),
    }


def presence(db: Session, client_id: UUID, first: date | None, last: date) -> dict[str, Any] | None:
    """AI presence from the newest completed run in [first, last]: the share of answers that name or cite the brand."""
    runs = _runs(db, client_id, first, last)
    if not runs:
        return None
    out = _shares(_responses(db, [runs[0].id]))
    if out is None:
        return None
    return {**out, "run_date": runs[0].started_at.date()}


def daily_presence(db: Session, client_id: UUID, first: date, last: date) -> dict[date, dict[str, float]]:
    """One reading per day that has a completed run (the day's newest run)."""
    out: dict[date, dict[str, float]] = {}
    for run in _runs(db, client_id, first, last):
        day = run.started_at.date()
        if day in out:
            continue
        shares = _shares(_responses(db, [run.id]))
        if shares:
            out[day] = {"mention_pct": shares["mention_pct"], "cited_pct": shares["cited_pct"]}
    return out


def latest_run_date(db: Session, client_id: UUID, last: date) -> date | None:
    runs = _runs(db, client_id, None, last)
    return runs[0].started_at.date() if runs else None


def prompt_readings(db: Session, client_id: UUID, end: date, first: date | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """The newest dated answer for each (platform, prompt) on or before `end`. Keyed by platform key and lower-cased prompt."""
    readings: dict[tuple[str, str], dict[str, Any]] = {}
    for run in _runs(db, client_id, first, end):
        for r in _responses(db, [run.id]):
            if r.visibility_type is None or r.visibility_type == "Error":
                continue
            key = (r.platform, r.query_text.strip().lower())
            if key in readings:
                continue
            readings[key] = {
                "observed_on": run.started_at.date().isoformat(), "prompt": r.query_text, "platform": r.platform,
                "brand_mentioned": bool(r.brand_mentioned) and not r.asked_by_name, "brand_cited": bool(r.url_cited),
                "asked_by_name": bool(r.asked_by_name), "source": SOURCE, "llm_id": r.platform,
            }
    return readings
