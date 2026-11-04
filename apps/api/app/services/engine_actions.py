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
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.annotation import Annotation, AnnotationType
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
    steps: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    check_after_days: int | None = None


def slots_in_record(record: dict) -> dict[str, RecordSlot]:
    """Every uid the saved record offers.

    `candidates` is in here as well as `actions`: an action the engine left
    out can be put into the plan, and from that moment it is assigned, sent
    and measured like any other. Only the slotted ones carry a slot number.

    The retainer pools are read the same way under their own kind, so
    assignment, the Teamwork send, skipping and the results loop all work
    on a refresh without knowing it is one.
    """
    out: dict[str, RecordSlot] = {}
    for kind, key in (
        ("action", "actions"),
        ("incident", "incidents"),
        # Retainer work. A separate kind because it is inside the monthly
        # fee and a growth action is not, and the two are reported apart.
        ("update", "updates"),
        ("content", "new_content"),
        ("action", "candidates"),
        ("update", "update_candidates"),
        ("content", "content_candidates"),
    ):
        for row in record.get(key) or []:
            uid = row.get("action_uid")
            if not uid or uid in out:
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
                steps=tuple(row.get("steps") or []),
                evidence=tuple(row.get("evidence") or []),
                check_after_days=row.get("check_after_days"),
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
    assignee_email: str | None,
    assignee_name: str | None = None,
    due: date | None,
    db_user_id: uuid.UUID | None = None,
) -> EngineAction:
    """Hand the slot to somebody, by email.

    Email rather than a user id, because most of the team does the work and
    never opens this tool — of the eight people in Teamwork, four had an
    account here and the rest could not be assigned anything. `db_user_id`
    is filled where the person also has one, so anything keyed on OrganicIQ
    users still resolves.

    Clearing the assignee returns the slot to `planned` rather than leaving it
    `assigned` with nobody on it — a state that reads as handled and is not.
    """
    email = (assignee_email or "").strip().lower() or None
    row = _row_for(db, client, month, slot)
    row.assignee_email = email
    row.assignee_name = (assignee_name or "").strip() or None
    row.assignee_user_id = db_user_id
    row.due = due
    row.status = "assigned" if email else "planned"
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
    row.assignee_email = None
    row.assignee_name = None
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
    # Sent after it was shipped: the entry already exists and gains its task.
    if task_id:
        logged = (
            db.query(Annotation)
            .filter(Annotation.client_id == client.id, Annotation.engine_uid == slot.uid)
            .one_or_none()
        )
        if logged is not None:
            logged.teamwork_task_id = task_id
    db.flush()
    return row


#: What kind of entry shipping each kind of slot writes to the account history.
_SHIPPED_TYPE = {
    "content": AnnotationType.CONTENT_PUBLISHED,
    "update": AnnotationType.CONTENT_UPDATED,
    "incident": AnnotationType.TECHNICAL_CHANGE,
    "action": AnnotationType.GROWTH_ACTION,
}


def _log_shipped(
    db: Session, client: Client, slot: RecordSlot, row: EngineAction, *, on: date | None
) -> None:
    """Keep the account history in step with what has been marked shipped.

    Shipping writes one entry and shipping it again updates that entry rather
    than adding a second. Clearing the date removes it, which is the "marked the
    wrong one" case: the entry exists only because of the date. Entries a person
    typed or imported have no `engine_uid` and are never touched here.
    """
    existing = (
        db.query(Annotation)
        .filter(Annotation.client_id == client.id, Annotation.engine_uid == slot.uid)
        .one_or_none()
    )
    if on is None:
        if existing is not None:
            db.delete(existing)
        return
    fields = {
        "date": on,
        "completed_at": on,
        "annotation_type": _SHIPPED_TYPE.get(slot.kind, AnnotationType.GROWTH_ACTION),
        "description": slot.title,
        "page_url": slot.target_url or None,
        "success_metric": slot.metric,
        "teamwork_task_id": row.teamwork_task_id,
        "measurement_start_date": on + timedelta(days=1),
        "measurement_end_date": on + timedelta(days=slot.check_after_days or 28),
    }
    if existing is None:
        db.add(Annotation(client_id=client.id, engine_uid=slot.uid, **fields))
    else:
        for key, value in fields.items():
            setattr(existing, key, value)


def mark_shipped(
    db: Session,
    client: Client,
    slot: RecordSlot,
    month: str,
    *,
    on: date | None,
) -> EngineAction:
    """Record the day the work went live.

    The results loop reads this to tell "the metric did not move" from "the
    metric did not move and nobody did the work". Without it every verdict
    carries the unshipped caveat, and a warning on every row is a warning
    nobody reads.

    Clearing it is allowed: somebody marks the wrong slot eventually.
    """
    row = _row_for(db, client, month, slot)
    if on != row.shipped_on:
        row.after_value = None
        row.result = None
        row.before_value = None
        if on is not None:
            from app.services.results import measure, metric_key_for
            from app.services.plan_review import workflow_record
            record = load_record(db, client, month)
            data = workflow_record(record.record) if record else {}
            action = next((a for key in ("actions", "updates", "new_content", "candidates")
                           for a in data.get(key, []) if a.get("action_uid") == slot.uid), {})
            reading = measure(db, client, metric_key_for(action),
                              url=slot.target_url, term=action.get("term"),
                              as_of=on - timedelta(days=1))
            row.before_value = reading.value
    row.shipped_on = on
    row.status = "done" if on is not None else ("assigned" if row.assignee_email else "planned")
    row.action_id = slot.action_id
    row.target_url = slot.target_url
    _log_shipped(db, client, slot, row, on=on)
    db.flush()
    return row


def set_in_plan(
    db: Session,
    client: Client,
    slot: RecordSlot,
    month: str,
    *,
    in_plan: bool | None,
    reason: str | None = None,
) -> EngineAction:
    """Put an action in the month's plan, or take it out.

    `None` hands the decision back to the engine rather than freezing
    whatever it last said, so a re-run with better data can change its mind
    about anything nobody has an opinion on.
    """
    row = _row_for(db, client, month, slot)
    row.in_plan = in_plan
    row.in_plan_reason = (reason or "").strip() or None
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
        "assignee_email": row.assignee_email,
        "assignee_name": row.assignee_name,
        "due": row.due.isoformat() if row.due else None,
        "skip_reason": row.skip_reason,
        "in_plan": row.in_plan,
        "in_plan_reason": row.in_plan_reason,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "shipped_on": row.shipped_on.isoformat() if row.shipped_on else None,
        "teamwork_task_id": row.teamwork_task_id,
        "teamwork_task_url": row.teamwork_task_url,
        "assigned_action_id": row.action_id,
        "before_value": float(row.before_value) if row.before_value is not None else None,
        "after_value": float(row.after_value) if row.after_value is not None else None,
        "result": row.result,
        "stale": stale,
    }
