"""Business Intelligence for v2: drill-downs for any date range, and the change log."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.annotation import Annotation
from app.models.client import Client
from app.models.config import OrganicChannel
from app.services import bi

router = APIRouter(prefix="/v2/bi", tags=["v2 business intelligence"])

MAX_RANGE_DAYS = 800


@router.get("")
def business_intelligence(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
    channel: str | None = None,
) -> dict:
    if end < start or (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a start before the end, no more than about two years apart.")
    if channel and channel not in {c.value for c in OrganicChannel}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That is not a channel.")
    return bi.build(db, client, start, end, channel or None)


class NoteIn(BaseModel):
    date: date
    description: str = Field(min_length=3, max_length=2000)
    page: str | None = Field(default=None, max_length=2048)


@router.post("/changes", status_code=status.HTTP_201_CREATED)
def add_change(
    payload: NoteIn,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    note = bi.add_note(db, client, payload.date, payload.description, payload.page)
    return {"id": str(note.id)}


@router.delete("/changes/{change_id}")
def remove_change(
    change_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Only a note a person typed can be removed here; an entry written by marking a part done is removed by marking it not done."""
    row = db.query(Annotation).filter(Annotation.id == change_id, Annotation.client_id == client.id).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That entry is not on this client.")
    if row.engine_uid is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This entry came from the plan. Mark its part not done on the plan to remove it.")
    db.delete(row)
    db.commit()
    return {"ok": True}
