"""Annotations: everything marked done on the plan, and anything else worth tying to the numbers (an event, a trade show, a campaign, a site change), with what happened to the page's numbers afterwards."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.core.urls import normalize_url
from app.models.annotation import Annotation, AnnotationResult
from app.models.client import Client
from app.services import annotations as annotation_service
from app.schemas import AnnotationCreate

router = APIRouter(prefix="/v2/annotations", tags=["v2-annotations"])

TYPE_LABELS = {
    "growth_action": "Growth action", "event": "Event or trade show", "content_published": "New content", "content_updated": "Content change", "technical_change": "Technical change",
    "website_change": "Website change", "conversion_change": "Conversion change", "campaign_change": "Campaign change", "algorithm_event": "Search update", "manual_note": "Note",
}


def _from_plan(row: Annotation) -> dict | None:
    """Where an entry written by marking a part done came from: `task:<task id>:<part position>`."""
    if not row.engine_uid or not row.engine_uid.startswith("task:"):
        return None
    _, task_id, index = row.engine_uid.split(":")
    return {"task_id": task_id, "part": int(index)}


def _out(row: Annotation) -> dict:
    summary = row.impact_summary_json or {}
    kind = row.annotation_type.value
    return {
        "id": str(row.id), "date": row.date.isoformat(), "type": kind, "type_label": TYPE_LABELS.get(kind, kind), "description": row.description, "page": row.page_url,
        "from_plan": _from_plan(row), "how": "Seen live on the page" if row.verified_how else "Marked done on the plan" if row.engine_uid else "Added by hand", "verified_how": row.verified_how, "notes": row.notes, "result": row.result.value,
        "measure_from": row.measurement_start_date.isoformat() if row.measurement_start_date else None,
        "measure_to": row.measurement_end_date.isoformat() if row.measurement_end_date else None,
        "baseline": summary.get("baseline") or {}, "after": summary.get("post") or {}, "changes": summary.get("deltas") or {}, "waiting": summary.get("measurement_note"),
    }


@router.get("")
def list_completed(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[str | None, Query(max_length=2048)] = None,
) -> dict:
    """Newest first. With `page`, only what was done to that page. Entries still inside their 28 days are re-measured as they are read."""
    rows = annotation_service.list_annotations(db, client.id)
    if page:
        target = normalize_url(page)
        rows = [r for r in rows if r.page_url and normalize_url(r.page_url) == target]
    changed = False
    for r in rows:
        if r.result in (AnnotationResult.NOT_YET_MEASURED, AnnotationResult.NOT_ENOUGH_DATA) and r.measurement_end_date:
            annotation_service.measure_annotation_impact(db, client, r, persist=False)
            changed = True
    if changed:
        db.commit()
    out = [_out(r) for r in rows]
    return {"manual_types": [{"key": k, "label": TYPE_LABELS[k]} for k in MANUAL_TYPES], "entries": out, "counts": {"total": len(out), "from_plan": sum(1 for e in out if e["from_plan"]), "improved": sum(1 for e in out if e["result"] == "improved")}, "types": TYPE_LABELS}


#: What a person can add by hand. Everything but a plain note is followed for 28 days after its date, like work marked done on the plan.
MANUAL_TYPES = ["event", "campaign_change", "website_change", "technical_change", "algorithm_event", "manual_note"]


class NoteIn(BaseModel):
    date: date
    description: str = Field(min_length=3, max_length=2000)
    page: str | None = Field(default=None, max_length=2048)
    type: Literal["event", "campaign_change", "website_change", "technical_change", "algorithm_event", "manual_note"] = "manual_note"


@router.post("", status_code=status.HTTP_201_CREATED)
def add_note(
    payload: NoteIn,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    measured = payload.type != "manual_note"
    row = annotation_service.create_annotation(db, client, AnnotationCreate(
        date=payload.date, annotation_type=payload.type, description=payload.description.strip(), page_url=payload.page or None,
        completed_at=payload.date if measured else None, measurement_start_date=payload.date if measured else None,
        measurement_end_date=payload.date + timedelta(days=28) if measured else None,
    ))
    return {"id": str(row.id)}


class Edit(BaseModel):
    notes: str | None = Field(default=None, max_length=4000)
    result: Literal["improved", "no_meaningful_change", "declined", "not_enough_data", "not_yet_measured"] | None = None


@router.patch("/{annotation_id}")
def edit(
    annotation_id: UUID,
    payload: Edit,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Add a note, or say what the result was when the measured one does not tell the story."""
    row = annotation_service.get_annotation(db, client.id, annotation_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That entry is not on this client.")
    if payload.notes is not None:
        row.notes = payload.notes.strip() or None
    if payload.result is not None:
        row.result = AnnotationResult(payload.result)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/{annotation_id}")
def remove(
    annotation_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Only a note typed by hand can be removed here; an entry from the plan is removed by marking its part not done."""
    row = annotation_service.get_annotation(db, client.id, annotation_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That entry is not on this client.")
    if row.engine_uid is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This entry came from the plan. Mark its part not done on the plan to remove it.")
    db.delete(row)
    db.commit()
    return {"ok": True}
