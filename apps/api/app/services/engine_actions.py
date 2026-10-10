"""What the team did about a prescribed action.

The saved record is what the engine decided; nothing here may change it. This
module owns the other half — who it went to, when it was sent, whether it was
skipped and why — in `engine_actions`, keyed by the slot uid so an assignment
survives a re-run of the same month.

Every write is checked against the saved record first. A uid that is not in
the record for that month is refused: without that check the endpoint is an
open write to a table keyed by a string the caller chooses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.decision import EngineAction, MonthlyRecord

#: The states a slot can be in. `done` is set by the results loop, not here.
STATUSES = frozenset({"planned", "assigned", "done", "skipped"})


@dataclass(frozen=True)
class RecordSlot:
    """A slot as the saved record describes it."""

    uid: str
    kind: str
    action_id: str | None
    target_url: str | None
    title: str
    done_when: str | None
    why: str | None
    metric: str | None
    check_on: str | None
    effort_min: int | None


def slots_in_record(record: dict) -> dict[str, RecordSlot]:
    """Every uid the saved record offers, actions and incidents alike."""
    out: dict[str, RecordSlot] = {}
    for kind, key in (("action", "actions"), ("incident", "incidents")):
        for row in record.get(key) or []:
            uid = row.get("action_uid")
            if not uid:
                continue
            out[uid] = RecordSlot(
                uid=uid,
                kind=kind,
                action_id=row.get("id"),
                target_url=row.get("target_url"),
                title=row.get("title") or "",
                done_when=row.get("done_when"),
                why=row.get("why"),
                metric=row.get("metric"),
                check_on=row.get("check_on"),
                effort_min=row.get("effort_min"),
            )
    return out


def load_record(db: Session, client: Client, month: str) -> MonthlyRecord | None:
    return (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.client_id == client.id, MonthlyRecord.month == month)
        .one_or_none()
    )


def list_workflow(db: Session, client: Client, month: str) -> list[EngineAction]:
    return (
        db.query(EngineAction)
        .filter(EngineAction.client_id == client.id, EngineAction.month == month)
        .all()
    )


def _row_for(
    db: Session, client: Client, month: str, slot: RecordSlot
) -> EngineAction:
    row = (
        db.query(EngineAction)
        .filter(EngineAction.client_id == client.id, EngineAction.uid == slot.uid)
        .one_or_none()
    )
    if row is None:
        row = EngineAction(
            uid=slot.uid,
            client_id=client.id,
            month=month,
            kind=slot.kind,
            status="planned",
        )
        db.add(row)
    return row


def assign(
    db: Session,
    client: Client,
    slot: RecordSlot,
    month: str,
    *,
    assignee_user_id: uuid.UUID | None,
    due: date | None,
) -> EngineAction:
    """Hand the slot to somebody.

    Clearing the assignee returns the slot to `planned` rather than leaving it
    `assigned` with nobody on it — a state that reads as handled and is not.
    """
    row = _row_for(db, client, month, slot)
    row.assignee_user_id = assignee_user_id
    row.due = due
    row.status = "assigned" if assignee_user_id else "planned"
    row.skip_reason = None
    # Provenance: what this slot held at the moment somebody took it on.
    row.action_id = slot.action_id
    row.target_url = slot.target_url
    db.flush()
    return row


def skip(
    db: Session, client: Client, slot: RecordSlot, month: str, *, reason: str
) -> EngineAction:
    """Take the slot off the table, with the reason on the record.

    A reason is required. "Skipped" with no reason is the state that makes
    next month's run unable to say whether the action was wrong or the month
    was busy.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("A skip needs a reason.")
    row = _row_for(db, client, month, slot)
    row.status = "skipped"
    row.skip_reason = reason
    row.assignee_user_id = None
    row.due = None
    row.action_id = slot.action_id
    row.target_url = slot.target_url
    db.flush()
    return row


def unskip(db: Session, client: Client, slot: RecordSlot, month: str) -> EngineAction:
    row = _row_for(db, client, month, slot)
    row.status = "planned"
    row.skip_reason = None
    db.flush()
    return row


def mark_sent(
    db: Session,
    client: Client,
    slot: RecordSlot,
    month: str,
    *,
    task_id: str | None = None,
    task_url: str | None = None,
) -> EngineAction:
    """Record that the slot left the building."""
    row = _row_for(db, client, month, slot)
    row.sent_at = datetime.now(timezone.utc)
    if task_id:
        row.teamwork_task_id = task_id
    if task_url:
        row.teamwork_task_url = task_url
    if row.status == "planned":
        row.status = "assigned"
    row.action_id = slot.action_id
    row.target_url = slot.target_url
    db.flush()
    return row


def serialise(row: EngineAction, *, slot: RecordSlot | None = None) -> dict:
    """One row as the page reads it.

    `stale` is the point of keeping `action_id` and `target_url`: it is true
    when the slot now holds a different action from the one that was on screen
    when somebody acted on it, which a re-run can cause.
    """
    stale = bool(
        slot is not None
        and row.action_id is not None
        and (row.action_id != slot.action_id or row.target_url != slot.target_url)
    )
    return {
        "uid": row.uid,
        "status": row.status,
        "assignee_user_id": str(row.assignee_user_id) if row.assignee_user_id else None,
        "due": row.due.isoformat() if row.due else None,
        "skip_reason": row.skip_reason,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "teamwork_task_id": row.teamwork_task_id,
        "teamwork_task_url": row.teamwork_task_url,
        "assigned_action_id": row.action_id,
        "stale": stale,
    }
