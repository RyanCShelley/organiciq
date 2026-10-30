"""Tasks confirmed from the Decision engine: confirm, plan, send to Teamwork, mark shipped.

Confirming is the human step. A prescription a rule produced and an unconfirmed suggestion
become tasks the same way, and the Teamwork description says which it was.

The monthly allowance is a count, not a gate: it says how many of the plan's growth actions
are used, and an operator who confirms more is told they are over it, not stopped.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.core.settings import get_settings
from app.integrations import teamwork
from app.models.client import Client
from app.models.engine_task import EngineTask
from app.services.monthly_review import parse_month
from app.services import task_results
from app.services.plan_allowances import resolve_plan_allowances

router = APIRouter(prefix="/v2/engine/tasks", tags=["v2 engine tasks"])

COUNTED = ("confirmed", "sent", "shipped")


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


class TaskUpdate(BaseModel):
    assignee_email: str | None = None
    due: date | None = None
    status: Literal["confirmed", "shipped", "dropped"] | None = None
    #: Distinguishes "leave it" from "clear it" for the two optional fields.
    clear_assignee: bool = False
    clear_due: bool = False


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
        "status": task.status,
        "confirmed_by": task.confirmed_by,
        "confirmed_at": task.confirmed_at.isoformat() if task.confirmed_at else None,
        "assignee_email": task.assignee_email,
        "due": task.due.isoformat() if task.due else None,
        "teamwork_task_id": task.teamwork_task_id,
        "teamwork_task_url": task.teamwork_task_url,
        "shipped_at": task.shipped_at.isoformat() if task.shipped_at else None,
        "check_on": task.check_on.isoformat() if task.check_on else None,
    }


def _month(value: str) -> str:
    try:
        parse_month(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return value


def _pages_used(rows) -> int:
    """Growth actions are sold by the page: however many tasks a page has, it is one."""
    return len({r.page_url for r in rows if r.status in COUNTED})


def _allowance(client: Client, used: int) -> dict:
    try:
        monthly = resolve_plan_allowances(client).growth_action_allowance
    except ValueError:  # no tier set
        monthly = None
    return {"monthly": monthly, "used": used, "over": monthly is not None and used > monthly}


def _get(db: Session, client: Client, task_id: UUID) -> EngineTask:
    task = db.query(EngineTask).filter(EngineTask.id == task_id, EngineTask.client_id == client.id).one_or_none()
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
    task = (
        db.query(EngineTask)
        .filter(
            EngineTask.client_id == client.id,
            EngineTask.month == month,
            EngineTask.rule_id == payload.rule_id,
            EngineTask.search == search,
            EngineTask.page_url == payload.page,
        )
        .one_or_none()
    )
    created = task is None
    if task is None:
        task = EngineTask(
            client_id=client.id, month=month, kind=payload.kind, rule_id=payload.rule_id, search=search,
            page_url=payload.page, confirmed_by=user.email,
        )
        db.add(task)
    elif task.status == "dropped":
        # Confirming again after dropping it brings it back, as a fresh yes from whoever says it.
        task.status, task.confirmed_by, task.confirmed_at = "confirmed", user.email, datetime.now(timezone.utc)
        created = True
    if created:
        task.title, task.why, task.steps = payload.title, payload.why, list(payload.steps)
        task.done_when, task.metric, task.effort_min = payload.done_when, payload.metric, payload.effort_min
        task.evidence = list(payload.evidence)
    db.commit()
    db.refresh(task)
    used = _pages_used(db.query(EngineTask).filter(EngineTask.client_id == client.id, EngineTask.month == month).all())
    return {"created": created, "task": _out(task), "allowance": _allowance(client, used)}


@router.patch("/{task_id}")
def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    task = _get(db, client, task_id)
    if payload.clear_assignee:
        task.assignee_email = None
    elif payload.assignee_email is not None:
        task.assignee_email = payload.assignee_email.strip().lower() or None
    if payload.clear_due:
        task.due = None
    elif payload.due is not None:
        task.due = payload.due
    if payload.status is not None:
        if payload.status == "confirmed" and task.teamwork_task_id:
            task.status = "sent"  # it already went to Teamwork; it cannot be unsent from here
        else:
            task.status = payload.status
        task.shipped_at = datetime.now(timezone.utc) if payload.status == "shipped" else None
        if payload.status == "shipped":
            task_results.take_baseline(db, client, task)
    db.commit()
    db.refresh(task)
    return _out(task)


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
        # Parts are headed by "# " lines; the steps under a heading are its checklist.
        lines = [f"\n{step[2:]}" if step.startswith("# ") else f"  [ ] {step}" for step in task.steps]
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
    """Push the task to the client's Teamwork tasklist. Idempotent: a second press returns the first task."""
    task = _get(db, client, task_id)
    if task.teamwork_task_id:
        return _out(task)
    if task.status == "dropped":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This task was dropped. Confirm it again first.")
    if not teamwork.configured():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Teamwork is not set up on this install, so the task can be copied but not sent.")
    if not client.teamwork_tasklist_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This client has no Teamwork tasklist yet. Choose one in Settings → Connections.")

    assignee = None
    if task.assignee_email:
        try:
            assignee = teamwork.person_id_for(task.assignee_email, teamwork.list_people())
        except teamwork.TeamworkError:
            assignee = None  # sent unassigned rather than not sent
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
    db.refresh(task)
    return _out(task)


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
