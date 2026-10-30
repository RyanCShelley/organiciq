"""What a shipped growth action did: the page and topic before it shipped, against the same after.

The baseline is taken when a task is marked shipped: the 28 days before. The result is worked out once the 28
days after are complete in Search Console (which finalises days late), then kept, so it never changes.

For a topic, it counts the searches that contain it on the page worked, in Search Console: clicks,
impressions, and average position. For the AI platforms, it compares whether the latest run before the work
cited the site for the topic's paired question with the latest run since.

No verdict is given. A small page moves by noise, so the numbers are shown with a note when the starting
numbers are too small to read much into. Position is better when it is lower.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions import visibility_candidates as vc
from app.models.client import Client
from app.models.engine_task import EngineTask
from app.models.gsc import FactGscQueryPage
from app.models.llm_visibility import LlmResponse, LlmRun
from app.services import llm_evidence

WINDOW_DAYS = 28
#: Search Console finalises a day two to three days late.
LAG_DAYS = 3
#: Below this many impressions before the work, a change is too small to say much about.
SMALL_BASELINE_IMPRESSIONS = 100


def _gsc(db: Session, client: Client, keyword: str, page: str, start: date, end: date) -> dict[str, Any]:
    key = " ".join(keyword.lower().split())
    rows = vc._aggregate(db, client.id, start, end, [key])
    clicks = impressions = weighted = 0.0
    for (_, url), n in rows.items():
        if url != page:
            continue
        clicks += n["clicks"]
        impressions += n["impressions"]
        weighted += n["position"] * n["impressions"]
    return {
        "clicks": round(clicks),
        "impressions": round(impressions),
        "position": round(weighted / impressions, 1) if impressions else None,
    }


def _ai(db: Session, client: Client, keyword: str, *, at_or_before: datetime | None = None, after: datetime | None = None) -> dict[str, Any] | None:
    """Whether the AI platforms cited the site for the topic's paired question, in the latest run before or since."""
    paired = llm_evidence.paired_keyword(db, client, keyword)
    if paired is None:
        return None
    query = db.query(LlmRun).filter(LlmRun.client_id == client.id, LlmRun.status == "completed")
    if at_or_before is not None:
        query = query.filter(LlmRun.started_at <= at_or_before)
    if after is not None:
        query = query.filter(LlmRun.started_at > after)
    run = query.order_by(LlmRun.started_at.desc()).first()
    if run is None:
        return None
    prompt = " ".join(paired.paired_ai_prompt.split()).lower()
    rows = [
        r for r in db.query(LlmResponse).filter(LlmResponse.run_id == run.id)
        if r.visibility_type != "Error" and " ".join(r.query_text.split()).lower() == prompt
    ]
    if not rows:
        return None
    return {"run_date": run.started_at.date().isoformat(), "cited": sum(bool(r.url_cited) for r in rows), "platforms": len(rows)}


def take_baseline(db: Session, client: Client, task: EngineTask) -> None:
    """Record the 28 days before shipping. Called when a task is marked shipped."""
    shipped = (task.shipped_at or datetime.now(timezone.utc)).date()
    start, end = shipped - timedelta(days=WINDOW_DAYS), shipped - timedelta(days=1)
    task.baseline = {
        "window": [start.isoformat(), end.isoformat()],
        "gsc": _gsc(db, client, task.search, task.page_url, start, end),
        "ai": _ai(db, client, task.search, at_or_before=task.shipped_at or datetime.now(timezone.utc)),
    }
    task.check_on = shipped + timedelta(days=WINDOW_DAYS + LAG_DAYS)
    task.outcome = None
    task.outcome_at = None


def _newest_gsc_day(db: Session, client: Client) -> date | None:
    return db.query(func.max(FactGscQueryPage.date)).filter(FactGscQueryPage.client_id == client.id).scalar()


def _delta(after: dict[str, Any], before: dict[str, Any]) -> dict[str, Any]:
    pos = None if after["position"] is None or before["position"] is None else round(after["position"] - before["position"], 1)
    return {"clicks": after["clicks"] - before["clicks"], "impressions": after["impressions"] - before["impressions"], "position": pos}


def evaluate(db: Session, client: Client, task: EngineTask, today: date | None = None) -> dict[str, Any]:
    """The task's result so far: measuring until the days after are in, then the before and after numbers."""
    today = today or date.today()
    out: dict[str, Any] = {
        "task_id": str(task.id),
        "title": task.title,
        "topic": task.search,
        "page": task.page_url,
        "kind": task.kind,
        "shipped_on": task.shipped_at.date().isoformat() if task.shipped_at else None,
        "check_on": task.check_on.isoformat() if task.check_on else None,
    }
    if task.baseline is None or task.shipped_at is None:
        return {**out, "status": "no_baseline"}

    if task.outcome is None:
        shipped = task.shipped_at.date()
        end = shipped + timedelta(days=WINDOW_DAYS)
        newest = _newest_gsc_day(db, client)
        if today < task.check_on or newest is None or newest < end:
            return {**out, "status": "measuring", "before": task.baseline["gsc"], "ai_before": task.baseline.get("ai")}
        task.outcome = {
            "window": [(shipped + timedelta(days=1)).isoformat(), end.isoformat()],
            "gsc": _gsc(db, client, task.search, task.page_url, shipped + timedelta(days=1), end),
            "ai": _ai(db, client, task.search, after=task.shipped_at),
        }
        task.outcome_at = datetime.now(timezone.utc)
        db.commit()

    before, after = task.baseline["gsc"], task.outcome["gsc"]
    small = before["impressions"] < SMALL_BASELINE_IMPRESSIONS
    return {
        **out,
        "status": "measured",
        "before": before,
        "after": after,
        "change": _delta(after, before),
        "ai_before": task.baseline.get("ai"),
        "ai_after": task.outcome.get("ai"),
        "note": (
            f"Only {before['impressions']} impressions in the 28 days before, so a change this size can be noise."
            if small
            else None
        ),
    }


def list_results(db: Session, client: Client, today: date | None = None) -> list[dict[str, Any]]:
    """Every task of the client that has shipped, newest first, each measured if its days are in."""
    tasks = (
        db.query(EngineTask)
        .filter(EngineTask.client_id == client.id, EngineTask.shipped_at.isnot(None), EngineTask.status == "shipped")
        .order_by(EngineTask.shipped_at.desc())
        .all()
    )
    return [evaluate(db, client, t, today) for t in tasks]
