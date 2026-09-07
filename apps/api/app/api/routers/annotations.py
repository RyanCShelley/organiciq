from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.schemas import (
    AnnotationCreate,
    AnnotationImportRequest,
    AnnotationImportResponse,
    AnnotationOut,
    AnnotationUpdate,
)
from app.services import annotations as annotation_service

router = APIRouter(prefix="/annotations", tags=["annotations"])


def _serialize(row) -> AnnotationOut:
    return AnnotationOut(
        id=row.id,
        client_id=row.client_id,
        decision_id=row.decision_id,
        date=row.date,
        annotation_type=row.annotation_type.value if row.annotation_type else "manual_note",
        growth_action=row.growth_action.value if row.growth_action else None,
        description=row.description,
        topic_id=row.topic_id,
        page_url=row.page_url,
        baseline_metrics_json=row.baseline_metrics_json or {},
        success_metric=row.success_metric,
        teamwork_task_id=row.teamwork_task_id,
        completed_at=row.completed_at,
        measurement_start_date=row.measurement_start_date,
        measurement_end_date=row.measurement_end_date,
        post_action_metrics_json=row.post_action_metrics_json or {},
        result=row.result.value if row.result else "not_yet_measured",
        notes=row.notes,
        impact_summary_json=row.impact_summary_json or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[AnnotationOut])
def list_annotations(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AnnotationOut]:
    return [_serialize(row) for row in annotation_service.list_annotations(db, client.id)]


@router.post("", response_model=AnnotationOut, status_code=status.HTTP_201_CREATED)
def create_annotation(
    payload: AnnotationCreate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> AnnotationOut:
    try:
        row = annotation_service.create_annotation(db, client, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _serialize(row)


@router.post("/import", response_model=AnnotationImportResponse)
def import_annotations(
    payload: AnnotationImportRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> AnnotationImportResponse:
    try:
        result = annotation_service.import_annotations_csv(db, client, payload.csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AnnotationImportResponse(**result)


@router.post("/remeasure")
def remeasure_annotations(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    count = annotation_service.remeasure_all(db, client)
    return {"remeasured": count}


@router.patch("/{annotation_id}", response_model=AnnotationOut)
def update_annotation(
    annotation_id: UUID,
    payload: AnnotationUpdate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> AnnotationOut:
    try:
        row = annotation_service.update_annotation(db, client, annotation_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    return _serialize(row)


@router.delete("/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_annotation(
    annotation_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    if not annotation_service.delete_annotation(db, client.id, annotation_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
