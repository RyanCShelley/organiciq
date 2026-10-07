from datetime import date as DateType
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client, user_can_access_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_admin, require_sma_staff
from app.models.client import Client
from app.schemas import (
    BaselineSnapshotApplyRequest,
    BaselineSnapshotPreviewOut,
    ClientCreate,
    ClientOut,
    ClientUpdate,
)
from app.services import baseline_snapshot, clients as client_service

from app.services.plan_allowances import resolve_plan_allowances

router = APIRouter(prefix="/clients", tags=["clients"])


def client_out(client: Client) -> ClientOut:
    """A client with its plan allowance already worked out.

    The number is a business rule about what the client is buying, so the
    server answers it. The web used to apply the rule itself, which meant
    fetching `/admin/tiers` — an endpoint a client-role user is forbidden
    to call, so the whole Decision Engine page failed for them.
    """
    out = ClientOut.model_validate(client)
    if client.tier is not None:
        allowances = resolve_plan_allowances(client, client.tier)
        out.growth_action_allowance = allowances.growth_action_allowance
        out.plan_label = f"{allowances.tier_name} plan"
    return out



@router.get("", response_model=list[ClientOut])
def list_clients(
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ClientOut]:
    return [client_out(c) for c in client_service.list_clients(db, user)]


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ClientOut:
    client = client_service.create_client(db, payload)
    return client_out(client)


@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: UUID,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> ClientOut:
    if not user_can_access_client(db, user, client_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this client")
    client = client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client_out(client)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: UUID,
    payload: ClientUpdate,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> ClientOut:
    if not user_can_access_client(db, user, client_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this client")
    client = client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    updated = client_service.update_client(db, client, payload)
    return client_out(updated)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_client(
    client_id: UUID,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    if not client_service.delete_client(db, client_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{client_id}/baseline/preview", response_model=BaselineSnapshotPreviewOut)
def preview_baseline_from_ga4(
    client_id: UUID,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    as_of: DateType | None = Query(default=None),
    lookback_days: int = Query(default=90, ge=7, le=365),
) -> BaselineSnapshotPreviewOut:
    if not user_can_access_client(db, user, client_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this client")
    client = client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    try:
        preview = baseline_snapshot.preview_baseline_from_ga4(
            db, client, as_of=as_of, lookback_days=lookback_days
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BaselineSnapshotPreviewOut.model_validate(preview)


@router.post("/{client_id}/baseline/from-ga4", response_model=BaselineSnapshotPreviewOut)
def apply_baseline_from_ga4(
    client_id: UUID,
    payload: BaselineSnapshotApplyRequest,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> BaselineSnapshotPreviewOut:
    if not user_can_access_client(db, user, client_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this client")
    client = client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    try:
        _, preview = baseline_snapshot.apply_baseline_from_ga4(
            db,
            client,
            monthly_lead_goal=payload.monthly_lead_goal,
            notes=payload.notes,
            as_of=payload.as_of,
            lookback_days=payload.lookback_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BaselineSnapshotPreviewOut.model_validate(preview)


@router.get("/current/context", response_model=ClientOut)
def current_client_context(
    client: Annotated[Client, Depends(require_client)],
) -> ClientOut:
    return client_out(client)
