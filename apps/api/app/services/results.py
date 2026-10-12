"""Did the action work?

Every prescription carries a metric and a date to judge it on. Nothing read
either one: `engine_actions` has had `before_value`, `after_value` and
`result` since the table was created and no code has ever written them, so
"Last month's results" was empty by construction and the engine could
prescribe forever without learning anything.

Two rules shape this module.

**Every metric is read as-of a date**, over a window ending there, from the
dated facts. That is what makes a `before` recoverable after the fact: an
action prescribed in September can still be measured against what September
knew, which is the only reason the first five actions are not already lost.

**Nobody is told an action failed when nobody did it.** `shipped_on` is set by
a person. Where it is absent the metric is still read and reported — the
numbers are real — but the row says so, because a verdict on work that may
never have happened is an accusation, not a measurement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.config import ConversionDefinition
from app.models.decision import EngineAction, MonthlyRecord
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscPage
from app.models.seranking import FactSerAiPresence, FactSerRanking
from app.services.triage_signals import MANAGED_CHANNELS

logger = logging.getLogger("organiciq.results")

#: The window each metric is averaged over, ending on the day being measured.
#: A single day of GSC is weather.
WINDOW_DAYS = 28

#: Below this relative move, the metric did not do anything worth a verdict.
#: A judgement, not a measurement — the raw before and after travel with it so
#: a reader can disagree.
MATERIAL_CHANGE = 0.05

#: Which way is better. Position is the one metric where down is up.
LOWER_IS_BETTER = frozenset({"term_position"})

#: Metrics that settle an argument rather than move a number.
NOT_MEASURED = frozenset({"decision"})

#: What each action is judged on, for records written before `metric_key` was
#: stored on them. Those records are the whole reason the loop had to be able
#: to measure backwards, and without this every one of their actions falls
#: back to "decision" and measures nothing.
METRIC_BY_ACTION = {
    "V-1": "term_position",
    "V-2": "ai_presence",
    "V-3": "term_position",
    "V-4": "term_position",
    "V-5": "term_position",
    "V-6": "decision",
    "T-1": "page_clicks",
    "T-2": "page_clicks",
    "T-3": "engagement_rate",
    "L-1": "page_lead_rate",
    "L-2": "page_lead_rate",
    "L-3": "page_lead_rate",
}


def metric_key_for(action: dict) -> str:
    """The key the action is judged on, stored or inferred from its id."""
    stored = (action.get("metric_key") or "").strip()
    if stored:
        return stored
    return METRIC_BY_ACTION.get((action.get("id") or "").strip().upper(), "decision")


@dataclass(frozen=True)
class Measurement:
    value: float | None
    #: Why there is no number, where there is none.
    missing: str | None = None
    #: Measured, and the term was outside the results we check. A real state
    #: and not a missing reading: 96% of SMA's tracked terms sit here, so
    #: treating it as "no data" would leave almost every visibility action
    #: permanently unjudged.
    unranked: bool = False


def _window(as_of: date) -> tuple[date, date]:
    return as_of - timedelta(days=WINDOW_DAYS - 1), as_of


def _term_position(
    db: Session, client_id: UUID, term: str | None, as_of: date
) -> Measurement:
    """The tracked position on the nearest reading at or before `as_of`.

    `facts_ser_rankings` is dated and was written and never read. This is what
    makes a September position recoverable in November.
    """
    if not term:
        return Measurement(None, "the action names no term")
    row = (
        db.query(FactSerRanking.position, FactSerRanking.date)
        .filter(
            FactSerRanking.client_id == client_id,
            func.lower(FactSerRanking.keyword) == term.strip().lower(),
            FactSerRanking.date <= as_of,
            FactSerRanking.position.isnot(None),
        )
        .order_by(FactSerRanking.date.desc())
        .first()
    )
    if row is None:
        return Measurement(None, f"no tracked position for “{term}” on or before {as_of}")
    # SE Ranking writes 0 or 101 for "not in the results we checked", which
    # `_rank` in triage_signals has always known and this did not: every
    # before reading came out as position zero.
    position = float(row[0])
    if not 0 < position <= 100:
        return Measurement(
            None,
            f"“{term}” was outside the top 100 on {row[1]}",
            unranked=True,
        )
    return Measurement(position)


def _page_clicks(db: Session, client_id: UUID, url: str | None, as_of: date) -> Measurement:
    if not url:
        return Measurement(None, "the action names no page")
    start, end = _window(as_of)
    total = (
        db.query(func.coalesce(func.sum(FactGscPage.clicks), 0))
        .filter(
            FactGscPage.client_id == client_id,
            FactGscPage.normalized_url == url,
            FactGscPage.date >= start,
            FactGscPage.date <= end,
        )
        .scalar()
    )
    if total is None:
        return Measurement(None, "no Search Console data for this page in the window")
    return Measurement(float(total))


def _engagement_rate(
    db: Session, client_id: UUID, url: str | None, as_of: date
) -> Measurement:
    if not url:
        return Measurement(None, "the action names no page")
    start, end = _window(as_of)
    sessions, engaged = (
        db.query(
            func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
            func.sum(FactGa4Traffic.engaged_sessions),
        )
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.normalized_url == url,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
            FactGa4Traffic.channel.in_(MANAGED_CHANNELS),
        )
        .one()
    )
    sessions = float(sessions or 0)
    if not sessions or engaged is None:
        return Measurement(None, "no engaged-session data for this page in the window")
    return Measurement(float(engaged) / sessions)


def _page_lead_rate(
    db: Session, client_id: UUID, url: str | None, as_of: date
) -> Measurement:
    if not url:
        return Measurement(None, "the action names no page")
    lead_events = [
        d.event_name
        for d in db.query(ConversionDefinition).filter(
            ConversionDefinition.client_id == client_id,
            ConversionDefinition.active.is_(True),
            ConversionDefinition.conversion_type == "lead",
        )
    ]
    if not lead_events:
        return Measurement(None, "no GA4 event is counted as a lead")

    start, end = _window(as_of)
    sessions = float(
        db.query(func.coalesce(func.sum(FactGa4Traffic.sessions), 0))
        .filter(
            FactGa4Traffic.client_id == client_id,
            FactGa4Traffic.normalized_url == url,
            FactGa4Traffic.date >= start,
            FactGa4Traffic.date <= end,
            FactGa4Traffic.channel.in_(MANAGED_CHANNELS),
        )
        .scalar()
        or 0
    )
    if not sessions:
        return Measurement(None, "no managed sessions on this page in the window")
    leads = float(
        db.query(func.coalesce(func.sum(FactGa4Event.event_count), 0))
        .filter(
            FactGa4Event.client_id == client_id,
            FactGa4Event.normalized_url == url,
            FactGa4Event.event_name.in_(lead_events),
            FactGa4Event.date >= start,
            FactGa4Event.date <= end,
            FactGa4Event.channel.in_(MANAGED_CHANNELS),
        )
        .scalar()
        or 0
    )
    return Measurement(leads / sessions * 100.0)


def _ai_presence(db: Session, client_id: UUID, as_of: date) -> Measurement:
    """Client-wide, because that is the grain SE Ranking reports it at.

    An AI-citation action is judged on the site's presence rather than the
    page's, and the row says so — claiming a per-page number here would be
    inventing one.
    """
    row = (
        db.query(FactSerAiPresence.overall_presence_pct)
        .filter(
            FactSerAiPresence.client_id == client_id,
            FactSerAiPresence.metric_date <= as_of,
            FactSerAiPresence.overall_presence_pct.isnot(None),
        )
        .order_by(FactSerAiPresence.metric_date.desc())
        .first()
    )
    if row is None:
        return Measurement(None, f"no AI presence reading on or before {as_of}")
    return Measurement(float(row[0]))


def measure(
    db: Session,
    client: Client,
    metric_key: str,
    *,
    url: str | None = None,
    term: str | None = None,
    as_of: date,
) -> Measurement:
    """One metric, as it read on `as_of`."""
    if metric_key in NOT_MEASURED:
        return Measurement(None, "this action settles a decision rather than moving a metric")
    if metric_key == "term_position":
        return _term_position(db, client.id, term, as_of)
    if metric_key == "page_clicks":
        return _page_clicks(db, client.id, url, as_of)
    if metric_key == "engagement_rate":
        return _engagement_rate(db, client.id, url, as_of)
    if metric_key == "page_lead_rate":
        return _page_lead_rate(db, client.id, url, as_of)
    if metric_key == "ai_presence":
        return _ai_presence(db, client.id, as_of)
    return Measurement(None, f"no reader for metric “{metric_key}”")


def verdict(metric_key: str, before: float | None, after: float | None) -> str:
    """improved, worse, no_change — or waiting, where there is nothing to say."""
    if before is None or after is None:
        return "waiting"
    if before == 0:
        return "no_change" if after == 0 else "improved"
    change = (after - before) / abs(before)
    if abs(change) < MATERIAL_CHANGE:
        return "no_change"
    better = change < 0 if metric_key in LOWER_IS_BETTER else change > 0
    return "improved" if better else "worse"


# ── The loop ────────────────────────────────────────────────────────────────


def _row_for(db: Session, client: Client, uid: str, month: str, kind: str) -> EngineAction:
    row = (
        db.query(EngineAction)
        .filter(EngineAction.client_id == client.id, EngineAction.uid == uid)
        .one_or_none()
    )
    if row is None:
        row = EngineAction(
            uid=uid, client_id=client.id, month=month, kind=kind, status="planned"
        )
        db.add(row)
    return row


def capture_before(
    db: Session, client: Client, record: MonthlyRecord, *, force: bool = False
) -> int:
    """Read each action's metric as it stood when the action was prescribed.

    Called when a record is saved, and able to run afterwards because every
    metric is read as-of a date. `force` re-reads a value already stored,
    which is only wanted when fixing a measurement that was wrong.
    """
    data = record.record or {}
    as_of = record.data_through or date.fromisoformat(f"{record.month}-01")
    written = 0
    for action in data.get("actions") or []:
        uid = action.get("action_uid")
        if not uid:
            continue
        existing = (
            db.query(EngineAction)
            .filter(EngineAction.client_id == client.id, EngineAction.uid == uid)
            .one_or_none()
        )
        if existing is not None and existing.before_value is not None and not force:
            continue
        reading = measure(
            db,
            client,
            metric_key_for(action),
            url=action.get("target_url"),
            term=action.get("term"),
            as_of=as_of,
        )
        # Measure first, then write. Creating the row up front left a junk
        # row behind for every action whose metric could not be read.
        if reading.value is None:
            continue
        row = existing or _row_for(db, client, uid, record.month, "action")
        row.before_value = reading.value
        row.action_id = action.get("id")
        row.target_url = action.get("target_url")
        written += 1
    db.commit()
    return written


def check_due(
    db: Session, client: Client, *, today: date | None = None
) -> list[EngineAction]:
    """Judge every action whose check date has arrived.

    An action with no `before_value` is left alone: without the reading it
    started from there is nothing to compare, and a verdict made against
    nothing is worse than an empty row.
    """
    today = today or date.today()
    judged: list[EngineAction] = []

    for record in (
        db.query(MonthlyRecord).filter(MonthlyRecord.client_id == client.id).all()
    ):
        for action in (record.record or {}).get("actions") or []:
            uid, check_on = action.get("action_uid"), action.get("check_on")
            if not uid or not check_on or date.fromisoformat(check_on) > today:
                continue
            row = (
                db.query(EngineAction)
                .filter(EngineAction.client_id == client.id, EngineAction.uid == uid)
                .one_or_none()
            )
            # `row` may legitimately not exist: an action whose term was
            # off the rankings when it was prescribed has no before reading
            # to store, and that is the most common start there is.
            if row is not None and row.after_value is not None:
                continue
            metric_key = metric_key_for(action)
            reading = measure(
                db,
                client,
                metric_key,
                url=action.get("target_url"),
                term=action.get("term"),
                as_of=today,
            )
            # "Still not ranking" is an outcome, not a gap. Skipping it left
            # an action that did not work reading as "not checked yet"
            # forever, which claims less than is known.
            if reading.value is None and not reading.unranked:
                continue

            before = (
                float(row.before_value)
                if row is not None and row.before_value is not None
                else None
            )
            if before is None:
                # No stored reading. It may be that the term was off the
                # rankings when it was prescribed, which is a real starting
                # state rather than a gap — and the measurement is as-of a
                # date, so that can be established now.
                started = measure(
                    db,
                    client,
                    metric_key,
                    url=action.get("target_url"),
                    term=action.get("term"),
                    as_of=record.data_through
                    or date.fromisoformat(f"{record.month}-01"),
                )
                if not started.unranked:
                    continue
                row = row or _row_for(db, client, uid, record.month, "action")
                row.action_id = action.get("id")
                row.target_url = action.get("target_url")
                row.after_value = reading.value
                # Off the rankings then, off them now.
                row.result = "no_change" if reading.unranked else "improved"
                judged.append(row)
                continue

            if reading.unranked:
                # It had a position when it was prescribed and has none now.
                row.after_value = None
                row.result = "worse"
                judged.append(row)
                continue

            row.after_value = reading.value
            row.result = verdict(metric_key, before, reading.value)
            if row.status == "assigned":
                row.status = "done"
            judged.append(row)

    db.commit()
    return judged


def previous_results(
    db: Session, client: Client, month: str, *, previous: str
) -> list[dict[str, Any]]:
    """Last month's actions and what became of them, for this month's record."""
    record = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.client_id == client.id, MonthlyRecord.month == previous)
        .one_or_none()
    )
    if record is None:
        return []

    rows = {
        r.uid: r
        for r in db.query(EngineAction).filter(
            EngineAction.client_id == client.id, EngineAction.month == previous
        )
    }
    out: list[dict[str, Any]] = []
    for action in (record.record or {}).get("actions") or []:
        uid = action.get("action_uid")
        row = rows.get(uid) if uid else None
        out.append(
            {
                "action_uid": uid,
                "title": action.get("title"),
                "target_url": action.get("target_url"),
                "metric": action.get("metric"),
                "before": float(row.before_value) if row and row.before_value is not None else None,
                "after": float(row.after_value) if row and row.after_value is not None else None,
                "result": (row.result if row else None) or "waiting",
                "check_on": action.get("check_on"),
                # A verdict on work nobody recorded doing is an accusation,
                # not a measurement. The numbers still travel; the row says
                # what is not known about them.
                "shipped": bool(row and row.shipped_on),
                "skipped": bool(row and row.status == "skipped"),
            }
        )
    return out
