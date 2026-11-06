"""Content optimizer: small changes to a page (the opening, terms worked in, an FAQ), written by a model from the page's search data."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.core.settings import get_settings
from app.core.urls import normalize_url
from app.models.client import Client
from app.models.engine_task import EngineTask
from app.services import content_optimizer, ctr_optimizer, model_spend, part_tools

router = APIRouter(prefix="/v2/optimizer", tags=["v2-optimizer"])


def _ready() -> bool:
    return bool(get_settings().anthropic_api_key.strip())


@router.get("")
def optimizer_queue(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """The parts of this month's approved actions that this tool carries out, and what each change is."""
    today = date.today()
    months = {today.strftime("%Y-%m"), (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")}
    tasks = db.query(EngineTask).filter(EngineTask.client_id == client.id, EngineTask.month.in_(months), EngineTask.status != "dropped").order_by(EngineTask.month.desc()).all()
    queue = []
    for task in tasks:
        for part in part_tools.describe(task.parts or part_tools.from_steps(task.steps or [])):
            if part["tool"] == "optimizer":
                queue.append({"task_id": str(task.id), "task_title": task.title, "month": task.month, "page": task.page_url, "part_id": part["id"], "part_name": part["name"], "kind": part["tool_kind"], "status": part["status"]})
    return {"kinds": content_optimizer.KINDS, "queue": queue, "model_ready": _ready()}


@router.get("/page")
def optimizer_page(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    url: Annotated[str, Query(min_length=8, max_length=2048)],
) -> dict:
    """One page: the searches the model will work from, and the latest result of each kind of change."""
    url = normalize_url(url) or url
    end = date.today()
    detail = ctr_optimizer.page_detail(db, client, url, end - timedelta(days=content_optimizer.RANGE_DAYS), end)
    return {
        "url": url, "title": detail["title"], "searches": detail["searches"], "searches_total": detail["searches_total"], "kinds": content_optimizer.KINDS,
        "drafts": {k: content_optimizer.latest(db, client, k, url) for k in content_optimizer.KINDS}, "model_ready": _ready(),
    }


class DraftIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    kind: Literal["opening", "terms", "faq"]
    depth: Literal["quick", "deep", "deepest"] = "quick"
    #: The page's text, pasted by a person when the site cannot be read.
    text: str | None = Field(default=None, max_length=60000)


@router.post("/draft", status_code=status.HTTP_202_ACCEPTED)
def write_draft(
    payload: DraftIn,
    background: BackgroundTasks,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Have the model write one change for a page. A draft: nothing is sent to the site, and no page allowance is used."""
    if not _ready():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The Anthropic key is not set on this install, so the model cannot be asked.")
    cap = get_settings().ask_monthly_cap_usd
    if float(model_spend.month_spend(db, client)) >= cap:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"This client has used its ${cap:.0f} for model questions this month. The limit resets on the 1st.")
    row = content_optimizer.start(db, client, payload.kind, normalize_url(payload.url) or payload.url, payload.depth, user.email, payload.text)
    background.add_task(content_optimizer.run, row.id)
    return {"id": str(row.id)}
