from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from typing import Annotated, Literal
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
from app.core.security import AuthUser, require_sma_admin, require_sma_staff
from app.models.user import UserRole
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
#: Pending OAuth handshakes, by state token.
#:
#: Single-use and random, so it does its CSRF job. What it did not do was
#: forget: a handshake nobody finished stayed in memory for the life of the
#: process, and this dict only ever grew. It is also per-process, so a
#: restart or a second instance loses a flow in progress — which reads to
#: the operator as "Google connect is flaky" rather than as a restart.
_OAUTH_STATE_TTL = timedelta(minutes=15)
_oauth_states: dict[str, dict] = {}


def _drop_expired_states(now: datetime) -> None:
    for token, meta in list(_oauth_states.items()):
        started = meta.get("started_at")
        if started is None or now - started > _OAUTH_STATE_TTL:
            _oauth_states.pop(token, None)


class SaveGscPropertyRequest(BaseModel):
    site_url: str
    role: Literal["primary", "secondary"] = "primary"


class DeleteGscPropertyRequest(BaseModel):
    site_url: str


class SaveGa4PropertyRequest(BaseModel):
    property_id: str


def _normalize_secondary_urls(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            url = item.strip()
            if url not in out:
                out.append(url)
    return out


def _scope_param() -> str:
    return " ".join(DATA_OAUTH_SCOPES)


def _upsert_google_credentials(db: Session, client_id: UUID, cred_payload: dict) -> None:
    # Workspace-shared: one Google Data OAuth grant applies to every client.
    propagate_google_credentials(db, cred_payload)


def _claimed_by_another_client(
    db: Session, client: Client, provider: IntegrationProvider, value: str
) -> bool:
    """Whether a different client already has this property connected.

    One Google grant sees every property in the workspace, so the property
    picker offers all of them. A staff member assigned to client A could pick
    client Y's, and the daily sync would then pull Y's data into A. A property
    already connected elsewhere needs an admin to move or share it.
    """
    for row in db.query(Integration).filter(
        Integration.provider == provider, Integration.client_id != client.id
    ):
        if (row.external_property_id or "").strip() == value:
            return True
        if value in _normalize_secondary_urls(row.gsc_secondary_site_urls):
            return True
    return False


def _refuse_if_claimed(
    db: Session, user: AuthUser, client: Client, provider: IntegrationProvider, value: str
) -> None:
    if user.role == UserRole.SMA_ADMIN:
        return
    # A client that lives in a folder of a larger site shares that site's
    # property by design (see Client.path_prefix).
    if client.path_prefix:
        return
    if _claimed_by_another_client(db, client, provider, value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That property is already connected to another client. Ask an admin to move or share it.",
        )


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
    # Admin only. The grant this flow produces is workspace-wide: the callback
    # copies it onto every client, replacing the one in place. Any staff member
    # could connect their own Google account here and swap the credential that
    # every client's sync runs on.
    user: Annotated[AuthUser, Depends(require_sma_admin)],
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
    now = datetime.now(timezone.utc)
    _drop_expired_states(now)
    _oauth_states[state] = {
        "client_id": str(client_id),
        "user_id": str(user.id),
        "started_at": now,
    }

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
        # Google's own error code, but it arrives on the query string and so
        # is caller-controlled: encoded, not interpolated, so it cannot add
        # parameters of its own to the URL we send the browser to.
        return RedirectResponse(
            f"{web}/clients?" + urlencode({"oauth": "error", "message": error})
        )
    _drop_expired_states(datetime.now(timezone.utc))
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

    account = db.query(Client).filter(Client.id == client_id).one_or_none()
    slug = account.slug if account is not None else str(client_id)
    return RedirectResponse(f"{web}/clients/{slug}/integrations?oauth=connected")


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
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> IntegrationOut:
    integration = _integration_for(db, client.id, IntegrationProvider.GSC)
    if integration is None or not client_has_google_credentials(db, client.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GSC not connected")

    site_url = payload.site_url.strip()
    if not site_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_url required")
    _refuse_if_claimed(db, user, client, IntegrationProvider.GSC, site_url)

    secondaries = _normalize_secondary_urls(integration.gsc_secondary_site_urls)
    primary = (integration.external_property_id or "").strip() or None

    if payload.role == "primary":
        if site_url in secondaries:
            secondaries = [url for url in secondaries if url != site_url]
        integration.external_property_id = site_url
        integration.gsc_secondary_site_urls = secondaries
    else:
        if primary is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Set a primary GSC property before adding a secondary",
            )
        if site_url == primary:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Site is already the primary GSC property",
            )
        if site_url not in secondaries:
            secondaries.append(site_url)
        integration.gsc_secondary_site_urls = secondaries

    integration.connection_status = ConnectionStatus.CONNECTED
    integration.error_message = None
    db.commit()
    db.refresh(integration)
    return IntegrationOut.model_validate(integration)


@router.delete("/integrations/gsc/property", response_model=IntegrationOut)
def delete_gsc_property(
    payload: DeleteGscPropertyRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> IntegrationOut:
    integration = _integration_for(db, client.id, IntegrationProvider.GSC)
    if integration is None or not client_has_google_credentials(db, client.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GSC not connected")

    site_url = payload.site_url.strip()
    if not site_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_url required")

    secondaries = _normalize_secondary_urls(integration.gsc_secondary_site_urls)
    primary = (integration.external_property_id or "").strip() or None

    if primary == site_url:
        if secondaries:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Remove secondary properties before clearing the primary",
            )
        integration.external_property_id = None
    elif site_url in secondaries:
        integration.gsc_secondary_site_urls = [url for url in secondaries if url != site_url]
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GSC property not found")

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
    user: Annotated[AuthUser, Depends(require_sma_staff)],
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
    _refuse_if_claimed(db, user, client, IntegrationProvider.GA4, property_id)

    integration.external_property_id = property_id
    integration.connection_status = ConnectionStatus.CONNECTED
    integration.error_message = None
    db.commit()
    db.refresh(integration)
    return IntegrationOut.model_validate(integration)
