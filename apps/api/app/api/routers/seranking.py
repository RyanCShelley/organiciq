from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.core.settings import get_settings
from app.ingestion.seranking.client import list_sites
from app.models.client import Client
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.schemas import IntegrationOut

router = APIRouter(tags=["seranking"])


class SaveSerankingPropertyRequest(BaseModel):
    site_id: str
    project_name: str | None = None


@router.get("/integrations/seranking/projects")
def seranking_projects(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    settings = get_settings()
    if not settings.se_ranking_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SE_RANKING_API_KEY not configured",
        )

    try:
        sites = list_sites(settings.se_ranking_api_key)
    except Exception as exc:  # noqa: BLE001
        integration = (
            db.query(Integration)
            .filter(
                Integration.client_id == client.id,
                Integration.provider == IntegrationProvider.SE_RANKING,
            )
            .one_or_none()
        )
        if integration:
            integration.connection_status = ConnectionStatus.ERROR
            integration.error_message = str(exc)
            db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    out: list[dict] = []
    for site in sites:
        site_id = site.get("id") or site.get("site_id")
        if site_id is None:
            continue
        out.append(
            {
                "site_id": str(site_id),
                "title": site.get("title") or site.get("name") or str(site_id),
                "url": site.get("url") or site.get("domain"),
            }
        )
    return out


@router.post("/integrations/seranking/property", response_model=IntegrationOut)
def save_seranking_property(
    payload: SaveSerankingPropertyRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> IntegrationOut:
    settings = get_settings()
    if not settings.se_ranking_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SE_RANKING_API_KEY not configured",
        )

    site_id = payload.site_id.strip()
    if not site_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_id required")

    integration = (
        db.query(Integration)
        .filter(
            Integration.client_id == client.id,
            Integration.provider == IntegrationProvider.SE_RANKING,
        )
        .one_or_none()
    )
    if integration is None:
        integration = Integration(client_id=client.id, provider=IntegrationProvider.SE_RANKING)
        db.add(integration)

    integration.external_property_id = site_id
    integration.external_account_id = (payload.project_name or "").strip() or None
    integration.connection_status = ConnectionStatus.CONNECTED
    integration.error_message = None
    db.commit()
    db.refresh(integration)
    return IntegrationOut.model_validate(integration)
