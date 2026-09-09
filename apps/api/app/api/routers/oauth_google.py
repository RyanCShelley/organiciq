from __future__ import annotations

import secrets
from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.client_scope import require_client, user_can_access_client
from app.core.crypto import decrypt_json
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.core.settings import get_settings
from app.ingestion.ga4.client import list_ga4_properties
from app.ingestion.google_auth import DATA_OAUTH_SCOPES
from app.ingestion.google_credentials import (
    access_token_for_client,
    client_has_google_credentials,
    propagate_google_credentials,
    workspace_google_refresh_token,
)
from app.ingestion.gsc.client import list_sites
from app.models.client import Client
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.schemas import IntegrationOut

router = APIRouter(tags=["oauth-google"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Short-lived in-memory state for local OAuth (single-process API). Durable store later if needed.
_oauth_states: dict[str, dict] = {}


class SaveGscPropertyRequest(BaseModel):
    site_url: str


class SaveGa4PropertyRequest(BaseModel):
    property_id: str


def _scope_param() -> str:
    return " ".join(DATA_OAUTH_SCOPES)


def _upsert_google_credentials(db: Session, client_id: UUID, cred_payload: dict) -> None:
    # Workspace-shared: one Google Data OAuth grant applies to every client.
    propagate_google_credentials(db, cred_payload)


def _integration_for(
    db: Session, client_id: UUID, provider: IntegrationProvider
) -> Integration | None:
    return (
        db.query(Integration)
        .filter(Integration.client_id == client_id, Integration.provider == provider)
        .one_or_none()
    )


def _access_token_for_google(db: Session, client_id: UUID, preferred: IntegrationProvider) -> tuple[str, Integration]:
    integration = _integration_for(db, client_id, preferred)
    if integration is None:
        fallback = (
            IntegrationProvider.GSC if preferred == IntegrationProvider.GA4 else IntegrationProvider.GA4
        )
        integration = _integration_for(db, client_id, fallback)
    if integration is None or not client_has_google_credentials(db, client_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google is not connected")

    try:
        token = access_token_for_client(db, client_id)
    except Exception as exc:  # noqa: BLE001
        integration.connection_status = ConnectionStatus.ERROR
        integration.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return token, integration


@router.get("/oauth/google/start")
def start_google_data_oauth(
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    client_id: UUID = Query(...),
) -> dict:
    settings = get_settings()
    if not settings.google_data_oauth_client_id or not settings.google_data_oauth_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GOOGLE_DATA_OAUTH_CLIENT_ID/SECRET not configured",
        )

    if not user_can_access_client(db, user, client_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this client")

    state = secrets.token_urlsafe(24)
    _oauth_states[state] = {"client_id": str(client_id), "user_id": str(user.id)}

    params = {
        "client_id": settings.google_data_oauth_client_id,
        "redirect_uri": settings.google_data_oauth_redirect_uri,
        "response_type": "code",
        "scope": _scope_param(),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return {"authorization_url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}"}


@router.get("/oauth/google/callback")
def google_data_oauth_callback(
    db: Annotated[Session, Depends(get_db)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings = get_settings()
    web = settings.web_app_url.rstrip("/")

    if error:
        return RedirectResponse(f"{web}/clients?oauth=error&message={error}")
    if not code or not state or state not in _oauth_states:
        return RedirectResponse(f"{web}/clients?oauth=error&message=invalid_state")

    meta = _oauth_states.pop(state)
    client_id = UUID(meta["client_id"])

    token_payload = {
        "code": code,
        "client_id": settings.google_data_oauth_client_id,
        "client_secret": settings.google_data_oauth_client_secret,
        "redirect_uri": settings.google_data_oauth_redirect_uri,
        "grant_type": "authorization_code",
    }
    with httpx.Client(timeout=30.0) as client:
        token_res = client.post(GOOGLE_TOKEN_URL, data=token_payload)
        if token_res.status_code >= 400:
            return RedirectResponse(f"{web}/clients?oauth=error&message=token_exchange_failed")
        tokens = token_res.json()

    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")
    if not refresh_token and not access_token:
        return RedirectResponse(f"{web}/clients?oauth=error&message=no_tokens")

    cred_payload = {
        "refresh_token": refresh_token,
        "token": access_token,
        "token_type": tokens.get("token_type", "Bearer"),
        "scope": tokens.get("scope", _scope_param()),
    }
    if not cred_payload["refresh_token"]:
        # Incremental reconnect can omit refresh_token; keep existing workspace grant.
        existing_rt = workspace_google_refresh_token(db)
        if not existing_rt:
            gsc = _integration_for(db, client_id, IntegrationProvider.GSC)
            ga4 = _integration_for(db, client_id, IntegrationProvider.GA4)
            for row in (gsc, ga4):
                if row and row.credentials:
                    try:
                        existing_rt = decrypt_json(row.credentials).get("refresh_token")
                    except Exception:  # noqa: BLE001
                        existing_rt = None
                    if existing_rt:
                        break
        cred_payload["refresh_token"] = existing_rt
    if not cred_payload["refresh_token"]:
        return RedirectResponse(f"{web}/clients?oauth=error&message=missing_refresh_token")

    _upsert_google_credentials(db, client_id, cred_payload)
    # propagate_google_credentials already commits

    return RedirectResponse(
        f"{web}/clients/{client_id}/integrations?oauth=connected"
    )


@router.get("/integrations/gsc/sites")
def gsc_sites(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    token, integration = _access_token_for_google(db, client.id, IntegrationProvider.GSC)
    try:
        sites = list_sites(token)
    except Exception as exc:  # noqa: BLE001
        integration.connection_status = ConnectionStatus.ERROR
        integration.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return [
        {
            "site_url": s.get("siteUrl"),
            "permission_level": s.get("permissionLevel"),
        }
        for s in sites
        if s.get("siteUrl")
    ]


@router.post("/integrations/gsc/property", response_model=IntegrationOut)
def save_gsc_property(
    payload: SaveGscPropertyRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> IntegrationOut:
    integration = _integration_for(db, client.id, IntegrationProvider.GSC)
    if integration is None or not client_has_google_credentials(db, client.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GSC not connected")

    integration.external_property_id = payload.site_url
    integration.connection_status = ConnectionStatus.CONNECTED
    integration.error_message = None
    db.commit()
    db.refresh(integration)
    return IntegrationOut.model_validate(integration)


@router.get("/integrations/ga4/properties")
def ga4_properties(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    token, integration = _access_token_for_google(db, client.id, IntegrationProvider.GA4)
    try:
        properties = list_ga4_properties(token)
    except Exception as exc:  # noqa: BLE001
        integration.connection_status = ConnectionStatus.ERROR
        integration.error_message = str(exc)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{exc}. Reconnect Google and grant Analytics access, and enable Analytics Admin API.",
        ) from exc
    return properties


@router.post("/integrations/ga4/property", response_model=IntegrationOut)
def save_ga4_property(
    payload: SaveGa4PropertyRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> IntegrationOut:
    integration = _integration_for(db, client.id, IntegrationProvider.GA4)
    if integration is None or not client_has_google_credentials(db, client.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GA4 not connected — reconnect Google to grant Analytics access",
        )

    property_id = payload.property_id.strip()
    if property_id and not property_id.startswith("properties/"):
        property_id = f"properties/{property_id}"
    if not property_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="property_id required")

    integration.external_property_id = property_id
    integration.connection_status = ConnectionStatus.CONNECTED
    integration.error_message = None
    db.commit()
    db.refresh(integration)
    return IntegrationOut.model_validate(integration)
