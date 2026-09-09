from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.models.job import DataWatermark
from app.schemas import DataWatermarkOut, SyncJobCreate, SyncJobOut
from app.services.jobs import (
    OverlappingJobError,
    cancel_active_jobs,
    enqueue_sync_job,
    list_sync_jobs,
)

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[SyncJobOut])
def get_jobs(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SyncJobOut]:
    return [SyncJobOut.model_validate(j) for j in list_sync_jobs(db, client.id)]


@router.post("/jobs", response_model=SyncJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: SyncJobCreate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> SyncJobOut:
    try:
        job = enqueue_sync_job(db, client.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OverlappingJobError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return SyncJobOut.model_validate(job)


@router.post("/jobs/cancel-active", response_model=list[SyncJobOut])
def cancel_active(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SyncJobOut]:
    jobs = cancel_active_jobs(db, client.id, message="Cancelled — stuck sync cleared")
    return [SyncJobOut.model_validate(j) for j in jobs]


@router.get("/watermarks", response_model=list[DataWatermarkOut])
def get_watermarks(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DataWatermarkOut]:
    rows = (
        db.query(DataWatermark)
        .filter(DataWatermark.client_id == client.id)
        .order_by(DataWatermark.source.asc())
        .all()
    )
    return [DataWatermarkOut.model_validate(r) for r in rows]
