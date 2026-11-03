"""CTR optimizer for v2: pages and searches earning fewer clicks than their position should."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.routers import v2_tasks
from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.services import ctr_optimizer

router = APIRouter(prefix="/v2/ctr", tags=["v2 ctr optimizer"])

MAX_RANGE_DAYS = 800


def _range(start: date, end: date) -> None:
    if end < start or (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a start before the end, no more than about two years apart.")


@router.get("")
def ctr_optimizer_report(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
) -> dict:
    _range(start, end)
    return ctr_optimizer.build(db, client, start, end)


@router.get("/page")
def ctr_optimizer_page(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    url: Annotated[str, Query(min_length=8, max_length=2048)],
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
) -> dict:
    _range(start, end)
    return ctr_optimizer.page_detail(db, client, url, start, end)


class PlanIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    start: date = Field(alias="from")
    end: date = Field(alias="to")


def _short(url: str) -> str:
    return urlsplit(url).path or "/"


@router.post("/plan")
def send_to_plan(
    payload: PlanIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Send this page's click-through shortfall to the Decision engine's plan for this month, as a task to rewrite its title and description."""
    _range(payload.start, payload.end)
    detail = ctr_optimizer.page_detail(db, client, payload.url, payload.start, payload.end)
    below = [s for s in detail["searches"] if s["below"]]
    if not below:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This page is not below the click-through benchmark in this range, so there is nothing to send.")
    extra = round(sum(s["extra_clicks"] for s in below))
    expected = sum(s["expected_clicks"] for s in detail["searches"])
    clicks = sum(s["clicks"] for s in detail["searches"])
    top = below[0]
    path = _short(payload.url)
    steps = [
        f"Open {path}. Its title is “{detail['title'] or '(none)'}”" + (f" ({detail['title_length']} characters)" if detail["title"] else "") + (f" and its description is “{detail['description']}”" if detail["description"] else " and it has no description") + ".",
        "These searches earn less than their position should: " + "; ".join(f"“{s['query']}” (position {s['position']}, {s['ctr']}% against {s['expected_ctr']}% expected)" for s in below[:3]) + ".",
        "Rewrite the title so it gives the answer or benefit those searches want, keeps the main term near the start, and stays under about 60 characters.",
        "Rewrite the description (about 150 characters) to give a reason to click: what the visitor gets, and what sets this page apart.",
        "Publish, then add a note to the change log with the date so the 28-day check measures this change.",
    ]
    task = v2_tasks.TaskIn(
        month=date.today().strftime("%Y-%m"), kind="suggestion", rule_id="S-5", search=top["query"], page=payload.url,
        title=f"Rewrite the title and description of {path} to earn more clicks",
        why=f"This page earns {clicks} clicks where the benchmark expects about {round(expected)} for its positions. Closing the gap on the {len(below)} search{'es' if len(below) != 1 else ''} below benchmark is worth about {extra} more clicks over the range.",
        steps=steps, done_when="The new title and description are live and recorded in the change log.",
        metric="Click-through rate for this page's searches in Search Console, 28 days after the change against 28 days before.", effort_min=30,
        evidence=[f"{payload.start.isoformat()} to {payload.end.isoformat()}: {clicks} clicks, {round(expected)} expected, about {extra} available."],
    )
    return v2_tasks.confirm_task(task, client, user, db)
