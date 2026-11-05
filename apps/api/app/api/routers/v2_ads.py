"""Ads Accelerator for v2: how a client's Google Ads did in a month, and the notes on work done on the account."""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.ads import AdsNote
from app.models.client import Client
from app.services import ads_report

router = APIRouter(prefix="/v2/ads", tags=["v2 ads accelerator"])

MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
Month = Annotated[str, Query(pattern=MONTH.pattern)]


@router.get("")
def ads_report_for_month(client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_staff)], db: Annotated[Session, Depends(get_db)], month: Month) -> dict:
    return ads_report.report(db, client, month)


@router.get("/summary")
def ads_summary_for_month(client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_staff)], db: Annotated[Session, Depends(get_db)], month: Month) -> dict:
    return ads_report.summary(db, client, month)


class NoteIn(BaseModel):
    date: date
    text: str = Field(min_length=3, max_length=1000)


@router.post("/notes")
def add_note(client: Annotated[Client, Depends(require_client)], user: Annotated[AuthUser, Depends(require_sma_staff)], db: Annotated[Session, Depends(get_db)], payload: NoteIn) -> dict:
    """Write down a change made to the account, so it shows under "Work completed" and splits the month into before and after."""
    note = AdsNote(client_id=client.id, date=payload.date, text=payload.text.strip(), created_by=user.email)
    db.add(note)
    db.commit()
    return {"id": str(note.id), "date": note.date.isoformat(), "text": note.text, "by": note.created_by}


@router.delete("/notes/{note_id}")
def delete_note(note_id: UUID, client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_staff)], db: Annotated[Session, Depends(get_db)]) -> dict:
    row = db.query(AdsNote).filter(AdsNote.id == note_id, AdsNote.client_id == client.id).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That note is not on this client.")
    db.delete(row)
    db.commit()
    return {"deleted": True}
