from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.schemas import IntegrationCreate, IntegrationOut, IntegrationUpdate
from app.services import clients as client_service

router = APIRouter(tags=["integrations"])


@router.get("/integrations", response_model=list[IntegrationOut])
def list_integrations(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[IntegrationOut]:
    rows = client_service.list_integrations(db, client.id)
    return [IntegrationOut.model_validate(r) for r in rows]


@router.post("/integrations", response_model=IntegrationOut, status_code=status.HTTP_201_CREATED)
def upsert_integration(
    payload: IntegrationCreate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> IntegrationOut:
    row = client_service.create_or_update_integration(db, client.id, payload)
    return IntegrationOut.model_validate(row)


@router.patch("/integrations/{integration_id}", response_model=IntegrationOut)
def patch_integration(
    integration_id: UUID,
    payload: IntegrationUpdate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> IntegrationOut:
    row = client_service.update_integration(db, client.id, integration_id, payload)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    return IntegrationOut.model_validate(row)
