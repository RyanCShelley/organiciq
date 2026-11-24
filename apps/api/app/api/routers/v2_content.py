"""Content gaps and content refreshes for v2: searches the site has no page for, and pages worth updating."""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import CONTENT_EDITOR_ROLES, AuthUser, require_content_editor, require_sma_staff
from app.core.settings import get_settings
from app.models.client import Client
from app.integrations import teamwork
from app.models.schema_tools import ContentItem, ContentState
from app.core.urls import normalize_url
from app.services import content_briefs, content_calendar, content_prompts, content_gaps_view, content_refresh, model_spend
from app.services.review_visibility import key_of

router = APIRouter(prefix="/v2/content", tags=["v2 content"])

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
Area = Literal["gap", "refresh"]


def _month(month: str) -> str:
    if not _MONTH.match(month):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a month like 2026-09.")
    return month


def _reject_nul_query(value: str | None, label: str = "Value") -> str | None:
    if value is not None and "\x00" in value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{label} cannot contain NUL characters.",
        )
    return value


def _reject_nul_value(value: str | None, label: str = "Value") -> str | None:
    if value is not None and "\x00" in value:
        raise ValueError(f"{label} cannot contain NUL characters.")
    return value


@router.get("/gaps")
def gaps(
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    ignored: bool = False,
) -> dict:
    _reject_nul_query(q, "Search query")
    return {**content_gaps_view.build(db, client, show_ignored=ignored, q=q), "calendar": content_calendar.index(db, client)["gap"], "can_edit": user.role in CONTENT_EDITOR_ROLES, "model_ready": bool(get_settings().anthropic_api_key.strip())}


@router.get("/gaps/brief")
def gap_brief(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    term: Annotated[str, Query(min_length=1, max_length=300)],
) -> dict:
    _reject_nul_query(term, "Search term")
    return {"draft": content_briefs.latest(db, client, "brief", term)}


@router.get("/topics")
def topics(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return {"draft": content_briefs.latest(db, client, "topics", "site"), "dismissed": sorted(content_gaps_view.ignored(db, client, "topic")), "model_ready": bool(get_settings().anthropic_api_key.strip())}


@router.get("/topics/detail")
def topic_detail(
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    label: Annotated[str, Query(min_length=1, max_length=80)],
) -> dict:
    """One suggested topic opened: its searches with the data on file for each, the brief if one was written, and where it stands on the calendar."""
    _reject_nul_query(label, "Topic label")
    found = content_briefs.topic_detail(db, client, label)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That topic is not in the latest list. Reload the list.")
    return {**found, "draft": content_briefs.latest(db, client, "tbrief", found["topic"]["label"]), "calendar": content_calendar.index(db, client)["topic"].get(found["topic"]["label"]),
            "can_edit": user.role in CONTENT_EDITOR_ROLES, "model_ready": bool(get_settings().anthropic_api_key.strip())}


@router.get("/refreshes")
def refreshes(
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    ignored: bool = False,
) -> dict:
    _reject_nul_query(q, "Search query")
    return {**content_refresh.build(db, client, _month(month or content_briefs.last_complete_month()), show_ignored=ignored, q=q), "calendar": content_calendar.index(db, client)["refresh"], "can_edit": user.role in CONTENT_EDITOR_ROLES, "model_ready": bool(get_settings().anthropic_api_key.strip())}


@router.get("/refreshes/page")
def refresh_page(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    url: Annotated[str, Query(min_length=8, max_length=2048)],
    month: Annotated[str | None, Query()] = None,
) -> dict:
    _reject_nul_query(url, "Page URL")
    month = _month(month or content_briefs.last_complete_month())
    url = normalize_url(url) or url
    return {**content_refresh.page_detail(db, client, month, url), "month": month, "plan": content_briefs.latest(db, client, "refresh", url)}


@router.get("/refreshes/search")
def refresh_search(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    query: Annotated[str, Query(min_length=1, max_length=300)],
    month: Annotated[str | None, Query()] = None,
) -> dict:
    """A search two or more pages are shown for, opened: each page's numbers, month by month, and who has led it."""
    _reject_nul_query(query, "Search query")
    found = content_refresh.competing_detail(db, client, _month(month or content_briefs.last_complete_month()), query)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search Console has no data for that search. Reload the list.")
    return found


class SetAside(BaseModel):
    area: Area
    key: str = Field(min_length=1, max_length=2048)

    @field_validator("key")
    @classmethod
    def _no_nul_key(cls, value: str) -> str:
        return _reject_nul_value(value, "Key") or ""


def _state_key(area: Area, raw_key: str) -> str:
    if area == "gap":
        cleaned = key_of(raw_key)
    else:
        cleaned = (raw_key or "").strip()
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Key cannot be blank.")
    return cleaned


@router.post("/ignore")
def ignore(
    payload: SetAside,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    norm_key = _state_key(payload.area, payload.key)
    existing_keys = {
        k
        for (k,) in db.query(ContentState.key).filter(
            ContentState.client_id == client.id,
            ContentState.area == payload.area,
        )
    }
    matched = (
        any(key_of(k) == norm_key for k in existing_keys)
        if payload.area == "gap"
        else norm_key in existing_keys
    )
    if not matched:
        db.add(ContentState(client_id=client.id, area=payload.area, key=norm_key, created_by=user.email))
        db.commit()
    return {"ok": True}


@router.post("/restore")
def restore(
    payload: SetAside,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    norm_key = _state_key(payload.area, payload.key)
    if payload.area == "gap":
        rows = (
            db.query(ContentState)
            .filter(ContentState.client_id == client.id, ContentState.area == payload.area)
            .all()
        )
        for row in rows:
            if key_of(row.key) == norm_key:
                db.delete(row)
    else:
        db.query(ContentState).filter(
            ContentState.client_id == client.id,
            ContentState.area == payload.area,
            ContentState.key == norm_key,
        ).delete()
    db.commit()
    return {"ok": True}


class TopicSetAside(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    restore: bool = False

    @field_validator("label")
    @classmethod
    def _no_nul_label(cls, value: str) -> str:
        return _reject_nul_value(value, "Topic label") or ""


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
    kind: Literal["brief", "refresh", "topics", "tbrief"]
    key: str = Field(min_length=1, max_length=2048)
    depth: Literal["quick", "deep", "deepest"] = "quick"
    month: str | None = None

    @field_validator("key")
    @classmethod
    def _no_nul_key(cls, value: str) -> str:
        return _reject_nul_value(value, "Key") or ""


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


# ---- the content calendar -----------------------------------------------------------------------------------------------------------


class CalendarIn(BaseModel):
    kind: Literal["new_page", "refresh"]
    title: str = Field(min_length=1, max_length=300)
    target: str = Field(min_length=1, max_length=2048)
    source_area: Literal["gap", "refresh", "topic", "manual"] = "manual"
    source_key: str | None = Field(default=None, max_length=2048)
    due: date | None = None
    assignee_email: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=8000)

    @field_validator("title", "target", "source_key", "assignee_email", "notes")
    @classmethod
    def _no_nul_fields(cls, value: str | None, info) -> str | None:
        return _reject_nul_value(value, info.field_name)


class CalendarPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    status: Literal["idea", "planned", "writing", "review", "published", "dropped"] | None = None
    due: date | None = None
    clear_due: bool = False
    assignee_email: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=8000)

    @field_validator("title", "assignee_email", "notes")
    @classmethod
    def _no_nul_fields(cls, value: str | None, info) -> str | None:
        return _reject_nul_value(value, info.field_name)


def _item(db: Session, client: Client, item_id: UUID, lock: bool = False) -> ContentItem:
    query = db.query(ContentItem).filter(ContentItem.id == item_id, ContentItem.client_id == client.id)
    # Sending takes the row lock: two presses would otherwise each make a Teamwork list and a task.
    item = (query.with_for_update() if lock else query).first()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That item is not on this client's calendar.")
    return item


@router.get("/calendar")
def calendar(
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    dropped: bool = False,
) -> dict:
    q = db.query(ContentItem).filter(ContentItem.client_id == client.id)
    q = q.filter(ContentItem.status == "dropped") if dropped else q.filter(ContentItem.status != "dropped")
    rows = q.order_by(ContentItem.due.is_(None), ContentItem.due, ContentItem.created_at).limit(content_calendar.LIMIT).all()
    return {
        "items": [content_calendar.out(r) for r in rows], "can_edit": user.role in CONTENT_EDITOR_ROLES,
        "teamwork": {"configured": teamwork.configured(), "project_id": client.teamwork_content_project_id},
        "counts": {s: sum(1 for r in rows if r.status == s) for s in content_calendar.STATUSES if s != "dropped"},
    }


@router.post("/calendar")
def calendar_add(
    payload: CalendarIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_content_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Put a gap, a page to refresh, or something else on the calendar. A gap or page already there is returned, not added twice."""
    if payload.source_area != "manual" and not payload.source_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Say which gap or page this comes from.")
    item, created = content_calendar.add(
        db, client, email=user.email, kind=payload.kind, title=payload.title, target=payload.target, source_area=payload.source_area,
        source_key=payload.source_key, due=payload.due, assignee_email=payload.assignee_email, notes=payload.notes,
    )
    return {**content_calendar.out(item), "created": created}


@router.patch("/calendar/{item_id}")
def calendar_update(
    item_id: UUID,
    payload: CalendarPatch,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_content_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    item = _item(db, client, item_id)
    if payload.title is not None:
        item.title = payload.title.strip()
    if payload.notes is not None:
        item.notes = payload.notes
    if payload.assignee_email is not None:
        item.assignee_email = payload.assignee_email.strip() or None
    if payload.clear_due:
        item.due = None
    elif payload.due is not None:
        item.due = payload.due
        if item.status == "idea" and payload.status is None:
            item.status = "planned"
    if payload.status is not None:
        content_calendar.set_status(item, payload.status)
    db.commit()
    db.refresh(item)
    return content_calendar.out(item)


@router.delete("/calendar/{item_id}")
def calendar_remove(
    item_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_content_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Take an item off the calendar. Its Teamwork task, if sent, is left in Teamwork."""
    db.delete(_item(db, client, item_id))
    db.commit()
    return {"ok": True}


@router.post("/calendar/{item_id}/send")
def calendar_send(
    item_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_content_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Make the item's own list in the client's Teamwork content project, with its task. A second press returns the first task."""
    item = _item(db, client, item_id, lock=True)
    if item.teamwork_task_id and len(item.teamwork_subtasks or {}) >= len(content_prompts.subtasks(item, client)):
        return content_calendar.out(item)
    if not teamwork.configured():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Teamwork is not set up on this install, so the item cannot be sent.")
    if not client.teamwork_content_project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This client has no Teamwork project for content yet. Choose one in Client settings, under Connections.")
    if not item.due:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Set a publish date (the due date) first: it goes in the Teamwork list's name.")
    try:
        pending = content_calendar.send(db, client, item)
    except teamwork.TeamworkError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {**content_calendar.out(item), "subtasks_pending": pending}
