from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_admin, require_sma_staff
from app.models.client import Client
from app.models.decision import DecisionStatus
from app.schemas import (
    DecisionEvaluateRequest,
    DecisionEvaluateResponse,
    DecisionOut,
    DecisionStatusUpdate,
    DecisionThresholdsOut,
    DecisionThresholdsUpdate,
)
from app.services import decisions as decision_service

router = APIRouter(prefix="/decisions", tags=["decisions"])


@router.get("", response_model=list[DecisionOut])
def list_decisions(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
) -> list[DecisionOut]:
    rows = decision_service.list_decisions(
        db,
        client.id,
        from_date=from_date,
        to_date=to_date,
    )
    return [DecisionOut.model_validate(row) for row in rows]


@router.post("/evaluate", response_model=DecisionEvaluateResponse)
def evaluate_decisions(
    payload: DecisionEvaluateRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> DecisionEvaluateResponse:
    if payload.from_date > payload.to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'from' must be on or before 'to'",
        )
    created, skipped = decision_service.evaluate_and_store(
        db,
        client,
        from_date=payload.from_date,
        to_date=payload.to_date,
    )
    return DecisionEvaluateResponse(
        created=[DecisionOut.model_validate(row) for row in created],
        skipped=skipped,
    )


@router.patch("/{decision_id}", response_model=DecisionOut)
def update_decision(
    decision_id: UUID,
    payload: DecisionStatusUpdate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> DecisionOut:
    try:
        new_status = DecisionStatus(payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc

    updated = decision_service.update_decision_status(
        db,
        client_id=client.id,
        decision_id=decision_id,
        status=new_status,
        dismissal_reason=payload.dismissal_reason,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    return DecisionOut.model_validate(updated)


@router.get("/thresholds", response_model=DecisionThresholdsOut)
def get_thresholds(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> DecisionThresholdsOut:
    return DecisionThresholdsOut(
        thresholds=decision_service.get_thresholds(db, client.id),
        defaults=decision_service.default_threshold_catalog(),
    )


@router.put("/thresholds", response_model=DecisionThresholdsOut)
def put_thresholds(
    payload: DecisionThresholdsUpdate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> DecisionThresholdsOut:
    merged = decision_service.upsert_thresholds(db, client.id, payload.thresholds)
    return DecisionThresholdsOut(
        thresholds=merged,
        defaults=decision_service.default_threshold_catalog(),
    )
