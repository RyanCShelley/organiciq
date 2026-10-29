"""What v2's Connections screen needs beyond the integrations the current tool already serves.

Google, Search Console, GA4 and SE Ranking keep using `/integrations/*` and
`/oauth/google/*`. This adds Bing, which has no integration row, and says whether
the install-wide keys are set so the screen can explain what is missing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.core.settings import get_settings
from app.integrations import bing, teamwork
from app.models.client import Client
from app.models.client_bing_site import ClientBingSite
from app.schemas.v2_connections import BingSiteChoice, BingSiteOut, BingSiteSet, ConnectionsOut

router = APIRouter(prefix="/v2/connections", tags=["v2 connections"])


def _bing_out(row: ClientBingSite | None) -> BingSiteOut | None:
    if row is None:
        return None
    return BingSiteOut(
        site_url=row.site_url, status=row.status, error=row.error, checked_at=row.checked_at
    )


def _key() -> str:
    return get_settings().bing_webmaster_api_key.strip()


def _norm(url: str) -> str:
    return url.strip().lower().rstrip("/")


@router.get("", response_model=ConnectionsOut)
def get_connections(
    client: Annotated[Client, Depends(require_client)],
    db: Annotated[Session, Depends(get_db)],
) -> ConnectionsOut:
    settings = get_settings()
    row = db.query(ClientBingSite).filter(ClientBingSite.client_id == client.id).one_or_none()
    return ConnectionsOut(
        teamwork_configured=teamwork.configured(),
        teamwork_tasklist_id=client.teamwork_tasklist_id,
        bing_key_configured=bool(_key()),
        bing=_bing_out(row),
        se_ranking_key_configured=bool(settings.se_ranking_api_key.strip()),
        google_connect_configured=bool(
            settings.google_data_oauth_client_id and settings.google_data_oauth_client_secret
        ),
    )


@router.get("/bing/sites", response_model=list[BingSiteChoice])
def bing_sites(
    _client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
) -> list[BingSiteChoice]:
    if not _key():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="BING_WEBMASTER_API_KEY not configured"
        )
    try:
        return [BingSiteChoice(**s) for s in bing.list_sites(_key())]
    except bing.BingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.put("/bing", response_model=BingSiteOut)
def set_bing_site(
    payload: BingSiteSet,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> BingSiteOut:
    site_url = payload.site_url.strip()
    if not site_url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter the site as Bing lists it, starting with https://",
        )

    state, error = "unchecked", None
    if _key():
        try:
            known = {_norm(s["url"]): s["verified"] for s in bing.list_sites(_key())}
        except bing.BingError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        if _norm(site_url) not in known:
            state, error = "error", "That site is not on the Bing Webmaster account this key belongs to."
        elif not known[_norm(site_url)]:
            state, error = "error", "Bing lists the site but it is not verified."
        else:
            state = "connected"

    row = db.query(ClientBingSite).filter(ClientBingSite.client_id == client.id).one_or_none()
    if row is None:
        row = ClientBingSite(client_id=client.id)
        db.add(row)
    row.site_url, row.status, row.error = site_url, state, error
    row.checked_at = datetime.now(timezone.utc) if _key() else None
    db.commit()
    db.refresh(row)
    return _bing_out(row)  # type: ignore[return-value]


@router.delete("/bing", status_code=status.HTTP_204_NO_CONTENT)
def clear_bing_site(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    db.query(ClientBingSite).filter(ClientBingSite.client_id == client.id).delete()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
