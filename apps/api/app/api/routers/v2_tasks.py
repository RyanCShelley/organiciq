"""Tasks confirmed from the Decision engine: confirm, plan, send to Teamwork, mark shipped.

Confirming is the human step. A prescription a rule produced and an unconfirmed suggestion
become tasks the same way, and the Teamwork description says which it was.

The monthly allowance is a count, not a gate: it says how many of the plan's growth actions
are used, and an operator who confirms more is told they are over it, not stopped.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.core.settings import get_settings
from app.core.urls import normalize_url, url_variants
from app.decisions.action_context import REJECTION_REASONS
from app.integrations import teamwork
from app.models.client import Client
from app.models.engine_task import INACTIVE_STATUSES, EngineTask
from app.services.monthly_review import parse_month
from app.services import part_done, part_tools, month_work, task_results, task_verify, teamwork_subtasks, teamwork_sync
from app.services.plan_allowances import resolve_plan_allowances

router = APIRouter(prefix="/v2/engine/tasks", tags=["v2 engine tasks"])

COUNTED = ("confirmed", "sent", "shipped")


class PartIn(BaseModel):
    id: str = Field(default="", max_length=16)
    name: str = Field(min_length=1, max_length=200)
    custom: bool = False


class TaskPartUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default="", max_length=16)
    name: str = Field(min_length=1, max_length=200)
    status: Literal["open", "done"] | None = None
    custom: bool | None = None


class TaskIn(BaseModel):
    month: str
    kind: Literal["prescription", "suggestion", "growth_action"]
    rule_id: str = Field(min_length=1, max_length=16)
    search: str = Field(min_length=1, max_length=400)
    page: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=500)
    why: str | None = None
    steps: list[str] = []
    done_when: str | None = None
    metric: str | None = None
    effort_min: int | None = Field(default=None, ge=0, le=100000)
    evidence: list[str] = []
    #: The parts of a growth action, in the order of the checklist, so each can point at its tool. Read from the steps when not sent.
    parts: list[PartIn] = []


class TaskRejectIn(BaseModel):
    month: str | None = None
    kind: Literal["prescription", "suggestion", "growth_action"] = "growth_action"
    rule_id: str = Field(default="GA", min_length=1, max_length=16)
    search: str = Field(default="(page)", min_length=1, max_length=400)
    page: str = Field(min_length=1, max_length=2048)
    title: str | None = Field(default=None, max_length=500)
    why: str | None = None
    steps: list[str] = []
    parts: list[PartIn] = []
    rejection_reason: str = Field(min_length=1, max_length=32)
    rejection_note: str | None = Field(default=None, max_length=2000)


class TaskUpdate(BaseModel):
    assignee_email: str | None = None
    due: date | None = None
    status: Literal["confirmed", "shipped", "dropped", "rejected"] | None = None
    rejection_reason: str | None = Field(default=None, max_length=32)
    rejection_note: str | None = Field(default=None, max_length=2000)
    steps: list[str] | None = None
    parts: list[TaskPartUpdate] | None = None
    #: Distinguishes "leave it" from "clear it" for the two optional fields.
    clear_assignee: bool = False
    clear_due: bool = False


def _validate_rejection_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    key = reason.strip()
    if key not in REJECTION_REASONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid rejection_reason '{reason}'. Expected one of: {', '.join(REJECTION_REASONS)}.",
        )
    return key


def _out(task: EngineTask) -> dict:
    return {
        "id": str(task.id),
        "month": task.month,
        "kind": task.kind,
        "rule_id": task.rule_id,
        "search": task.search,
        "page": task.page_url,
        "title": task.title,
        "why": task.why,
        "steps": task.steps or [],
        "done_when": task.done_when,
        "metric": task.metric,
        "effort_min": task.effort_min,
        "evidence": task.evidence or [],
        "parts": part_tools.describe(task.parts or part_tools.from_steps(task.steps or [])),
        "status": task.status,
        "confirmed_by": task.confirmed_by,
        "confirmed_at": task.confirmed_at.isoformat() if task.confirmed_at else None,
        "assignee_email": task.assignee_email,
        "due": task.due.isoformat() if task.due else None,
        "teamwork_task_id": task.teamwork_task_id,
        "teamwork_task_url": task.teamwork_task_url,
        "teamwork_subtasks": len(task.teamwork_subtasks or {}),
        "shipped_at": task.shipped_at.isoformat() if task.shipped_at else None,
        "check_on": task.check_on.isoformat() if task.check_on else None,
        "rejection_reason": task.rejection_reason,
        "rejection_reason_label": REJECTION_REASONS.get(task.rejection_reason) if task.rejection_reason else None,
        "rejection_note": task.rejection_note,
        "rejected_by": task.rejected_by,
        "rejected_at": task.rejected_at.isoformat() if task.rejected_at else None,
    }


def _month(value: str) -> str:
    try:
        parse_month(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return value


def _pages_used(rows) -> int:
    """Growth actions are sold by the page: however many tasks a page has, it is one."""
    return len({normalize_url(r.page_url) or r.page_url for r in rows if r.status in COUNTED})


def _find_task(db: Session, client: Client, month: str, rule_id: str, search: str, page_url: str) -> EngineTask | None:
    urls = url_variants(page_url) or [page_url]
    lower_urls = list({u.lower() for u in urls})
    return (
        db.query(EngineTask)
        .filter(
            EngineTask.client_id == client.id,
            EngineTask.month == month,
            EngineTask.rule_id == rule_id,
            EngineTask.search == search,
            or_(EngineTask.page_url.in_(urls), func.lower(EngineTask.page_url).in_(lower_urls)),
        )
        .order_by(EngineTask.confirmed_at.desc())
        .first()
    )


def _allowance(client: Client, used: int) -> dict:
    if client.service_mode == "consulting":
        return {"monthly": None, "used": used, "over": False}  # no monthly plan: the client's own team does the work
    try:
        monthly = resolve_plan_allowances(client).growth_action_allowance
    except ValueError:  # no tier set
        monthly = None
    return {"monthly": monthly, "used": used, "over": monthly is not None and used > monthly}


def _get(db: Session, client: Client, task_id: UUID, lock: bool = False) -> EngineTask:
    query = db.query(EngineTask).filter(EngineTask.id == task_id, EngineTask.client_id == client.id)
    # Sending takes the row lock, so a second press waits for the first and then finds its Teamwork id instead of making another task.
    task = (query.with_for_update() if lock else query).one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.get("/results")
def task_results_list(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    """What each shipped task did: the 28 days before against the 28 days after, once those are in."""
    return task_results.list_results(db, client)


_PEOPLE_CACHE: dict = {"at": 0.0, "rows": []}
_PEOPLE_TTL_SECONDS = 600


@router.get("/people")
def teamwork_people(_: Annotated[AuthUser, Depends(require_sma_staff)]) -> list[dict]:
    """Everyone in the Teamwork workspace, for the assignee picker. Kept for ten minutes so the plan page stays quick."""
    import time

    if not teamwork.configured():
        return []
    if time.time() - _PEOPLE_CACHE["at"] > _PEOPLE_TTL_SECONDS or not _PEOPLE_CACHE["rows"]:
        try:
            people = teamwork.list_people()
        except teamwork.TeamworkError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        _PEOPLE_CACHE.update(at=time.time(), rows=sorted(({"email": p.email, "name": p.name} for p in people), key=lambda r: (r["name"] or r["email"]).lower()))
    return _PEOPLE_CACHE["rows"]


@router.get("")
def list_tasks(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: str,
) -> dict:
    month = _month(month)
    rows = (
        db.query(EngineTask)
        .filter(EngineTask.client_id == client.id, EngineTask.month == month)
        .order_by(EngineTask.confirmed_at)
        .all()
    )
    used = _pages_used(rows)
    return {
        "month": month,
        "tasks": [_out(r) for r in rows],
        "allowance": _allowance(client, used),
        "teamwork": {"configured": teamwork.configured(), "tasklist_id": client.teamwork_tasklist_id},
        "work": month_work.build(db, client, month),
    }


@router.post("")
def confirm_task(
    payload: TaskIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Confirm a prescription or suggestion as a task. Confirming the same one twice returns the first."""
    month = _month(payload.month)
    search = " ".join(payload.search.lower().split())
    task = _find_task(db, client, month, payload.rule_id, search, payload.page)
    created = task is None
    if task is None:
        task = EngineTask(
            client_id=client.id, month=month, kind=payload.kind, rule_id=payload.rule_id, search=search,
            page_url=payload.page, confirmed_by=user.email,
        )
        db.add(task)
    elif task.status in INACTIVE_STATUSES:
        # Confirming again after dropping or rejecting brings it back, preserving "sent" if already pushed to Teamwork.
        task.status = "sent" if task.teamwork_task_id else "confirmed"
        task.confirmed_by, task.confirmed_at = user.email, datetime.now(timezone.utc)
        task.shipped_at = None
        task.rejection_reason = None
        task.rejection_note = None
        task.rejected_by = None
        task.rejected_at = None
        created = True
    if created:
        task.title, task.why, task.steps = payload.title, payload.why, list(payload.steps)
        task.done_when, task.metric, task.effort_min = payload.done_when, payload.metric, payload.effort_min
        task.evidence = list(payload.evidence)
        task.parts = [
            {
                "id": p.id,
                "name": p.name,
                "status": "open",
                **({"custom": True} if (p.custom or p.id == "CUSTOM") else {}),
            }
            for p in payload.parts
        ] or [{**p, "status": "open"} for p in part_tools.from_steps(task.steps)]
        task_verify.capture_before(db, client, task)  # the page as the crawl last saw it, to compare the live page with later
    db.commit()
    db.refresh(task)
    used = _pages_used(db.query(EngineTask).filter(EngineTask.client_id == client.id, EngineTask.month == month).all())
    return {"created": created, "task": _out(task), "allowance": _allowance(client, used)}


@router.post("/reject")
def reject_task(
    payload: TaskRejectIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Record a reviewer rejection with one of the 8 structured reasons, directly from Workbench/Diagnose or Plan."""
    reason = _validate_rejection_reason(payload.rejection_reason)
    month = _month(payload.month or datetime.now(timezone.utc).strftime("%Y-%m"))
    search = " ".join(payload.search.lower().split()) or "(page)"
    task = _find_task(db, client, month, payload.rule_id, search, payload.page)
    now = datetime.now(timezone.utc)
    if task is None:
        task = EngineTask(
            client_id=client.id,
            month=month,
            kind=payload.kind,
            rule_id=payload.rule_id,
            search=search,
            page_url=payload.page,
            title=payload.title or f"Rejected {payload.rule_id} on {payload.page}",
            why=payload.why,
            steps=list(payload.steps),
            parts=[
                {
                    "id": p.id,
                    "name": p.name,
                    "status": "open",
                    **({"custom": True} if (p.custom or p.id == "CUSTOM") else {}),
                }
                for p in payload.parts
            ],
            confirmed_by=user.email,
        )
        db.add(task)
    else:
        if task.parts:
            part_done.set_all(db, client, task, False, user.email)
        part_done.remove_all(db, client, task)
        if payload.title:
            task.title = payload.title
        if payload.why is not None:
            task.why = payload.why
        if payload.steps:
            task.steps = list(payload.steps)
        if payload.parts:
            task.parts = [
                {
                    "id": p.id or ("CUSTOM" if p.custom else ""),
                    "name": p.name,
                    "status": "open",
                    **({"custom": True} if (p.custom or p.id == "CUSTOM") else {}),
                }
                for p in payload.parts
            ]
    task.status = "rejected"
    task.shipped_at = None
    task.rejection_reason = reason
    task.rejection_note = (payload.rejection_note or "").strip() or None
    task.rejected_by = user.email
    task.rejected_at = now
    db.commit()
    db.refresh(task)
    return _out(task)


def _merge_parts(existing: list[dict], incoming: list[TaskPartUpdate], who: str | None = None) -> list[dict]:
    def _part_id(pid: str | None, is_custom: bool | None) -> str:
        raw = str(pid or "").strip()
        if not raw and is_custom:
            return "CUSTOM"
        return raw

    by_key = {
        (_part_id(p.get("id"), p.get("custom")), str(p.get("name") or "").strip().lower()): p
        for p in existing
    }
    now_iso = datetime.now(timezone.utc).isoformat()
    out: list[dict] = []
    for p in incoming:
        pid = _part_id(p.id, p.custom)
        name_key = p.name.strip().lower()
        prev = by_key.get((pid, name_key))
        if prev is None and pid == "CUSTOM":
            prev = by_key.get(("", name_key))
        item = dict(prev) if prev else {}
        item["id"] = pid or _part_id(item.get("id"), item.get("custom") or p.custom)
        item["name"] = p.name
        was_done = item.get("status") == "done"
        new_status = p.status or item.get("status") or "open"
        item["status"] = new_status
        if new_status == "done":
            if not item.get("done_at"):
                item["done_at"] = now_iso
            if not item.get("done_by") and who:
                item["done_by"] = who
            item.pop("no_auto", None)
        elif was_done and p.status == "open":
            item["done_at"] = None
            item["done_by"] = None
            item["done_how"] = None
            item["verified_at"] = None
            item["verified_how"] = None
            item["no_auto"] = True
        if p.custom or item["id"] == "CUSTOM":
            item["custom"] = True
        out.append(item)
    return out


def _sync_parts_from_steps(existing: list[dict], steps: list[str]) -> list[dict]:
    parsed = part_tools.from_steps(steps)
    if not parsed:
        return existing
    by_name = {str(p.get("name") or "").strip().lower(): p for p in existing}
    out: list[dict] = []
    for p in parsed:
        prev = by_name.get(p["name"].strip().lower())
        if prev:
            out.append(dict(prev))
        else:
            pid = p["id"] or "CUSTOM"
            item: dict = {"id": pid, "name": p["name"], "status": "open"}
            if pid == "CUSTOM":
                item["custom"] = True
            out.append(item)
    return out


@router.patch("/{task_id}")
def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    task = _get(db, client, task_id)
    reason = _validate_rejection_reason(payload.rejection_reason)
    if payload.clear_assignee:
        task.assignee_email = None
    elif payload.assignee_email is not None:
        task.assignee_email = payload.assignee_email.strip().lower() or None
    if payload.clear_due:
        task.due = None
    elif payload.due is not None:
        task.due = payload.due
    if payload.status in ("dropped", "rejected", "confirmed") and task.parts:
        part_done.set_all(db, client, task, False, user.email)
    if payload.steps is not None:
        task.steps = list(payload.steps)
        if payload.parts is None:
            task.parts = _sync_parts_from_steps(list(task.parts or []), task.steps)
    if payload.parts is not None:
        task.parts = _merge_parts(list(task.parts or []), payload.parts, who=user.email)
    if payload.status is not None:
        if payload.status == "confirmed" and task.teamwork_task_id:
            task.status = "sent"  # it already went to Teamwork; it cannot be unsent from here
        else:
            task.status = payload.status
        task.shipped_at = datetime.now(timezone.utc) if payload.status == "shipped" else None
        if payload.status == "shipped":
            task.rejection_reason = None
            task.rejection_note = None
            task.rejected_by = None
            task.rejected_at = None
            # Clean any annotations for removed/shifted indices, then mark every part done.
            part_done.sync_annotations(db, client, task, user.email)
            part_done.set_all(db, client, task, True, user.email)
            task_results.take_baseline(db, client, task)
        elif payload.status == "confirmed":
            task.rejection_reason = None
            task.rejection_note = None
            task.rejected_by = None
            task.rejected_at = None
            if task.parts:
                part_done.set_all(db, client, task, False, user.email)
            part_done.remove_all(db, client, task)
        elif payload.status in ("dropped", "rejected"):
            if reason is not None:
                task.rejection_reason = reason
            if payload.rejection_note is not None:
                task.rejection_note = payload.rejection_note.strip() or None
            if payload.status == "rejected" or reason is not None:
                task.rejected_by = user.email
                task.rejected_at = datetime.now(timezone.utc)
            if task.parts:
                part_done.set_all(db, client, task, False, user.email)
            part_done.remove_all(db, client, task)
    else:
        if reason is not None:
            task.rejection_reason = reason
            task.rejected_by = task.rejected_by or user.email
            task.rejected_at = task.rejected_at or datetime.now(timezone.utc)
        if payload.rejection_note is not None:
            task.rejection_note = payload.rejection_note.strip() or None
        if payload.steps is not None or payload.parts is not None:
            if task.status in INACTIVE_STATUSES:
                if task.parts:
                    part_done.set_all(db, client, task, False, user.email)
                part_done.remove_all(db, client, task)
            else:
                part_done.sync_annotations(db, client, task, user.email)
                part_done._settle(db, client, task)
    db.commit()
    db.refresh(task)
    return _out(task)


class PartDone(BaseModel):
    done: bool


@router.patch("/{task_id}/parts/{index}")
def mark_part(
    task_id: UUID,
    index: int,
    payload: PartDone,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Mark one part of an action done, or not done. Done writes an annotation for it; the action ships itself when every part is done."""
    task = _get(db, client, task_id)
    try:
        part_done.set_part(db, client, task, index, payload.done, user.email)
    except IndexError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _out(task)


@router.post("/{task_id}/check")
def check_live(
    task_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Ask Teamwork which subtasks are completed, then read the live page and mark done every part it shows. A part marked not done by a person is checked too, since this was asked for."""
    task = _get(db, client, task_id)
    tw = teamwork_sync.sync_task(db, client, task, force=True)  # subtasks finished in Teamwork mark their parts done first
    result = task_verify.check_task(db, client, task, force=True)
    db.refresh(task)
    return {"task": _out(task), "check": {**result, "teamwork": tw}}


def _description(task: EngineTask, client: Client) -> tuple[str, str]:
    name, text = teamwork.task_body(
        title=task.title,
        why=task.why,
        done_when=task.done_when,
        target_url=task.page_url,
        metric=task.metric,
        check_on=None,
        effort_min=task.effort_min,
        record_url=f"{get_settings().web_v2_app_url.rstrip('/')}/{client.slug}/engine",
    )
    if task.steps and task.kind == "growth_action":
        # Parts are headed by "#" lines; the steps under a heading are its checklist.
        lines = []
        for step in task.steps:
            stripped = step.strip()
            heading = re.match(r"^#(?!#)\s*(.+)$", stripped)
            lines.append(f"\n{heading.group(1).strip()}" if heading else f"  [ ] {step}")
        text += "\n\nChecklist" + "\n".join(lines)
    elif task.steps:
        text += "\n\nChecklist\n" + "\n".join(f"{i + 1}. {step}" for i, step in enumerate(task.steps))
    if task.evidence:
        text += "\n\nEvidence and limitations\n" + "\n".join(task.evidence)
    origin = (
        "Recommended by the Decision engine from a check of the page and its data."
        if task.kind == "prescription"
        else "A growth action from the Decision engine: one page, worked together for one topic. Its parts come from a live read of the page, Search Console and the AI platform runs, and a person chose them."
        if task.kind == "growth_action"
        else "Suggested by the Decision engine. The data to prove it was not available, so a person chose to do it."
    )
    text += f"\n\n{origin} Search: “{task.search}”. Confirmed by {task.confirmed_by} for {task.month}."
    return name, text


@router.post("/{task_id}/send")
def send_task(
    task_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Push the task to the client's Teamwork tasklist, with a subtask for each of its steps. Idempotent: a second press returns the first task
    and makes only the subtasks that are missing."""
    task = _get(db, client, task_id, lock=True)
    if task.status in INACTIVE_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This task was dropped or rejected. Confirm it again first.")
    subs = teamwork_subtasks.from_steps(task.steps or [], growth=task.kind == "growth_action")
    if task.teamwork_task_id and len(task.teamwork_subtasks or {}) >= min(len(subs), teamwork_subtasks.MAX_SUBTASKS):
        return _out(task)
    if not teamwork.configured():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Teamwork is not set up on this install, so the task can be copied but not sent.")
    assignee = teamwork_subtasks.assignee_id(task.assignee_email)
    if not task.teamwork_task_id:
        if not client.teamwork_tasklist_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This client has no Teamwork tasklist yet. Choose one in Settings → Connections.")
        name, description = _description(task, client)
        try:
            created = teamwork.create_task(
                tasklist_id=client.teamwork_tasklist_id,
                name=name,
                description=description,
                due=task.due.isoformat() if task.due else None,
                assignee_teamwork_id=assignee,
            )
        except teamwork.TeamworkError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        task.teamwork_task_id, task.teamwork_task_url = str(created["id"]), created["url"]
        if task.status == "confirmed":
            task.status = "sent"
        db.commit()
    pending = teamwork_subtasks.send(
        db, task, task.teamwork_task_id, subs,
        due=task.due.isoformat() if task.due else None, assignee=assignee,
    )
    db.refresh(task)
    return {**_out(task), "subtasks_pending": pending}


@router.get("/{task_id}/text")
def task_text(
    task_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """The task as plain text, for pasting where Teamwork is not available."""
    task = _get(db, client, task_id)
    name, description = _description(task, client)
    return {"name": name, "text": f"{name}\n\n{description}"}
