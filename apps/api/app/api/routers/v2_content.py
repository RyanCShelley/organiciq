"""Content gaps and content refreshes for v2: searches the site has no page for, and pages worth updating."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.core.settings import get_settings
from app.models.client import Client
from app.models.schema_tools import ContentState
from app.services import content_briefs, content_gaps_view, content_refresh, model_spend

router = APIRouter(prefix="/v2/content", tags=["v2 content"])

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
Area = Literal["gap", "refresh"]


def _month(month: str) -> str:
    if not _MONTH.match(month):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a month like 2026-09.")
    return month


@router.get("/gaps")
def gaps(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    ignored: bool = False,
) -> dict:
    return {**content_gaps_view.build(db, client, show_ignored=ignored, q=q), "model_ready": bool(get_settings().anthropic_api_key.strip())}


@router.get("/gaps/brief")
def gap_brief(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    term: Annotated[str, Query(min_length=1, max_length=300)],
) -> dict:
    return {"draft": content_briefs.latest(db, client, "brief", term)}


@router.get("/topics")
def topics(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return {"draft": content_briefs.latest(db, client, "topics", "site"), "dismissed": sorted(content_gaps_view.ignored(db, client, "topic")), "model_ready": bool(get_settings().anthropic_api_key.strip())}


@router.get("/refreshes")
def refreshes(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    ignored: bool = False,
) -> dict:
    return {**content_refresh.build(db, client, _month(month or content_briefs.last_complete_month()), show_ignored=ignored, q=q), "model_ready": bool(get_settings().anthropic_api_key.strip())}


@router.get("/refreshes/page")
def refresh_page(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    url: Annotated[str, Query(min_length=8, max_length=2048)],
    month: Annotated[str | None, Query()] = None,
) -> dict:
    month = _month(month or content_briefs.last_complete_month())
    return {**content_refresh.page_detail(db, client, month, url), "month": month, "plan": content_briefs.latest(db, client, "refresh", url)}


class SetAside(BaseModel):
    area: Area
    key: str = Field(min_length=1, max_length=2048)


@router.post("/ignore")
def ignore(
    payload: SetAside,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    if db.query(ContentState).filter(ContentState.client_id == client.id, ContentState.area == payload.area, ContentState.key == payload.key).first() is None:
        db.add(ContentState(client_id=client.id, area=payload.area, key=payload.key, created_by=user.email))
        db.commit()
    return {"ok": True}


@router.post("/restore")
def restore(
    payload: SetAside,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    db.query(ContentState).filter(ContentState.client_id == client.id, ContentState.area == payload.area, ContentState.key == payload.key).delete()
    db.commit()
    return {"ok": True}


class TopicSetAside(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    restore: bool = False


@router.post("/topics/dismiss")
def dismiss_topic(
    payload: TopicSetAside,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Mark a suggested topic as not in scope, so the finder never suggests it again."""
    content_briefs.set_aside_topic(db, client, payload.label, user.email, payload.restore)
    return {"ok": True}


class DraftIn(BaseModel):
    kind: Literal["brief", "refresh", "topics"]
    key: str = Field(min_length=1, max_length=2048)
    depth: Literal["quick", "deep", "deepest"] = "quick"
    month: str | None = None


@router.post("/draft", status_code=status.HTTP_202_ACCEPTED)
def write_draft(
    payload: DraftIn,
    background: BackgroundTasks,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Have the model write a brief, a refresh plan or a topic list. A draft: nothing is sent, and no page allowance is used."""
    if not get_settings().anthropic_api_key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The Anthropic key is not set on this install, so the model cannot be asked.")
    cap = get_settings().ask_monthly_cap_usd
    if float(model_spend.month_spend(db, client)) >= cap:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"This client has used its ${cap:.0f} for model questions this month. The limit resets on the 1st.")
    key = "site" if payload.kind == "topics" else payload.key
    row = content_briefs.start(db, client, payload.kind, key, payload.depth, user.email)
    if payload.kind == "refresh":
        row.payload = {"month": _month(payload.month or content_briefs.last_complete_month())}
        db.commit()
    background.add_task(content_briefs.run, row.id)
    return {"id": str(row.id)}
