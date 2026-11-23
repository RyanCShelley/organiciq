"""Marking a part of an action done: the plan, the annotation and the measurement stay in step.

Done is per part. Marking a part done writes one annotation for it (what changed, where, when, who said so), which is measured over the
next 28 days against the 28 before. Marking it not done removes that annotation. When every part is done the action ships itself and takes its
baseline; when a part is undone it comes back to the plan.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.annotation import Annotation, AnnotationType
from app.models.client import Client
from app.models.decision import GrowthAction
from app.models.engine_task import EngineTask
from app.services import annotations, part_tools, task_results

MEASURE_DAYS = 28

#: What kind of change each tool's work is, for the annotation: (annotation type, growth action it measures as).
_KIND = {
    "ctr": (AnnotationType.GROWTH_ACTION, GrowthAction.SERP_CTR),
    "inlinks": (AnnotationType.GROWTH_ACTION, GrowthAction.INTERNAL_LINKING),
    "schema": (AnnotationType.GROWTH_ACTION, GrowthAction.AI_VISIBILITY),
    "optimizer": (AnnotationType.CONTENT_UPDATED, None),
    "refresh": (AnnotationType.CONTENT_UPDATED, None),
    "gaps": (AnnotationType.CONTENT_PUBLISHED, None),
}


def uid(task: EngineTask, index: int) -> str:
    return f"task:{task.id}:{index}"


def parts_of(task: EngineTask) -> list[dict[str, Any]]:
    """The task's parts, read back from its checklist for a task made before they were stored. Position is a part's key."""
    if not task.parts:
        found = part_tools.from_steps(task.steps or []) or [{"id": task.rule_id if task.kind != "growth_action" else "", "name": task.title}]
        task.parts = [{**p, "status": "open"} for p in found]
    return [dict(p) for p in task.parts]


def _path(url: str) -> str:
    return urlsplit(url).path or "/"


def _write(db: Session, client: Client, task: EngineTask, index: int, part: dict[str, Any], today: date, who: str, verified: str | None = None) -> None:
    tool = part_tools.tool_for(str(part.get("id") or ""))
    kind, action = _KIND.get(tool["key"] if tool else "", (AnnotationType.WEBSITE_CHANGE, None))
    key = uid(task, index)
    row = db.query(Annotation).filter(Annotation.client_id == client.id, Annotation.engine_uid == key).one_or_none()
    if row is None:
        row = Annotation(client_id=client.id, engine_uid=key, date=today, annotation_type=kind, description="", baseline_metrics_json={})
        db.add(row)
    row.annotation_type, row.growth_action = kind, action
    row.date = row.completed_at = today
    row.description = f"{part['name']} on {_path(task.page_url)}"
    row.page_url = task.page_url
    row.success_metric = task.metric
    row.verified_how = verified
    row.teamwork_task_id = task.teamwork_task_id
    row.measurement_start_date, row.measurement_end_date = today, today + timedelta(days=MEASURE_DAYS)
    db.flush()
    annotations.measure_annotation_impact(db, client, row, persist=False)


def _remove(db: Session, client: Client, task: EngineTask, index: int) -> None:
    db.query(Annotation).filter(Annotation.client_id == client.id, Annotation.engine_uid == uid(task, index)).delete()


def set_part(db: Session, client: Client, task: EngineTask, index: int, done: bool, who: str, verified: str | None = None, how: str | None = None) -> EngineTask:
    parts = parts_of(task)
    if not 0 <= index < len(parts):
        raise IndexError("That part is not in this action.")
    today = datetime.now(ZoneInfo(client.timezone or "UTC")).date()
    part = parts[index]
    if done and part.get("status") != "done":
        part.update(status="done", done_at=datetime.now(timezone.utc).isoformat(), done_by=who)
        if how:
            part["done_how"] = how
        if verified:
            part.update(verified_at=part["done_at"], verified_how=verified)
        _write(db, client, task, index, part, today, who, verified)
    elif not done and part.get("status") == "done":
        # A person taking a part back is not to be overruled by the next live check.
        part.update(status="open", done_at=None, done_by=None, done_how=None, verified_at=None, verified_how=None, no_auto=True)
        _remove(db, client, task, index)
    task.parts = parts
    _settle(db, client, task)
    db.commit()
    db.refresh(task)
    return task


def _settle(db: Session, client: Client, task: EngineTask) -> None:
    """The action is shipped exactly when every part is done."""
    parts = task.parts or []
    all_done = bool(parts) and all(p.get("status") == "done" for p in parts)
    if all_done and task.status != "shipped":
        task.status, task.shipped_at = "shipped", datetime.now(timezone.utc)
        task_results.take_baseline(db, client, task)
    elif not all_done and task.status == "shipped":
        task.status, task.shipped_at = ("sent" if task.teamwork_task_id else "confirmed"), None


def remove_all(db: Session, client: Client, task: EngineTask) -> None:
    """Remove every Annotation row tied to this task."""
    db.query(Annotation).filter(
        Annotation.client_id == client.id,
        Annotation.engine_uid.like(f"task:{task.id}:%"),
    ).delete(synchronize_session=False)


def sync_annotations(db: Session, client: Client, task: EngineTask, who: str) -> None:
    """Keep Annotation rows synchronized with `task.parts` indices and done states after edits, deletions, or reordering."""
    parts = list(task.parts or [])
    done_uids = {uid(task, i) for i, p in enumerate(parts) if p.get("status") == "done"}
    existing_rows = (
        db.query(Annotation)
        .filter(
            Annotation.client_id == client.id,
            Annotation.engine_uid.like(f"task:{task.id}:%"),
        )
        .all()
    )
    by_uid = {row.engine_uid: row for row in existing_rows}
    for key, row in list(by_uid.items()):
        if key not in done_uids:
            db.delete(row)
            del by_uid[key]
    db.flush()

    today = datetime.now(ZoneInfo(client.timezone or "UTC")).date()
    now_iso = datetime.now(timezone.utc).isoformat()
    changed = False
    for i, part in enumerate(parts):
        if part.get("status") != "done":
            continue
        if not part.get("done_at"):
            part["done_at"] = now_iso
            changed = True
        if not part.get("done_by"):
            part["done_by"] = who
            changed = True
        key = uid(task, i)
        tool = part_tools.tool_for(str(part.get("id") or ""))
        expected_kind, expected_action = _KIND.get(tool["key"] if tool else "", (AnnotationType.WEBSITE_CHANGE, None))
        expected_desc = f"{part['name']} on {_path(task.page_url)}"
        row = by_uid.get(key)
        if row is None:
            _write(db, client, task, i, part, today, who, verified=part.get("verified_how"))
        elif (
            row.description != expected_desc
            or row.annotation_type != expected_kind
            or row.growth_action != expected_action
        ):
            # Another part shifted into this index; recreate cleanly so stale manual notes/results do not leak across parts.
            db.delete(row)
            db.flush()
            _write(db, client, task, i, part, today, who, verified=part.get("verified_how"))
    if changed:
        task.parts = [dict(p) for p in parts]


def set_all(db: Session, client: Client, task: EngineTask, done: bool, who: str) -> None:
    """Marking the whole action shipped marks every part done; taking it back reopens them. Commits."""
    parts = parts_of(task)
    today = datetime.now(ZoneInfo(client.timezone or "UTC")).date()
    for i, part in enumerate(parts):
        if done and part.get("status") != "done":
            part.update(status="done", done_at=datetime.now(timezone.utc).isoformat(), done_by=who)
            _write(db, client, task, i, part, today, who)
        elif not done and part.get("status") == "done":
            part.update(status="open", done_at=None, done_by=None, done_how=None, verified_at=None, verified_how=None)
            _remove(db, client, task, i)
    task.parts = parts
