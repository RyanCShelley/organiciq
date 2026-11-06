"""Ads Accelerator for v2: how a client's Google Ads did in a month."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_admin, require_sma_staff
from app.models.client import Client
from app.core.settings import get_settings
from app.integrations import google_ads
from app.services import ads_pull, ads_report

router = APIRouter(prefix="/v2/ads", tags=["v2 ads accelerator"])

MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
Month = Annotated[str, Query(pattern=MONTH.pattern)]


@router.get("")
def ads_report_for_month(client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_staff)], db: Annotated[Session, Depends(get_db)], month: Month) -> dict:
    return ads_report.report(db, client, month)


@router.get("/summary")
def ads_summary_for_month(client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_staff)], db: Annotated[Session, Depends(get_db)], month: Month) -> dict:
    return ads_report.summary(db, client, month)


@router.get("/connection")
def connection(client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_staff)], db: Annotated[Session, Depends(get_db)]) -> dict:
    """Where the Google Ads connection stands for this client: the permission, the account chosen, and how the last pull went."""
    return {
        "enabled": ads_report.enabled(client), "permission": google_ads.permission_granted(db), "manager_set": bool(google_ads.digits(get_settings().google_ads_login_customer_id)),
        "customer_id": client.google_ads_customer_id, "last_pull_at": client.google_ads_last_pull_at.isoformat() if client.google_ads_last_pull_at else None, "last_error": client.google_ads_last_error,
    }


@router.get("/accounts")
def accounts(_: Annotated[AuthUser, Depends(require_sma_admin)], db: Annotated[Session, Depends(get_db)]) -> dict:
    """The client accounts under the manager account, to choose from."""
    try:
        return {"accounts": google_ads.list_accounts(google_ads.access_token(db))}
    except google_ads.GoogleAdsError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


class AccountIn(BaseModel):
    customer_id: str | None = Field(default=None, max_length=30, description="Digits, dashes allowed. Empty to remove.")


@router.put("/connection")
def choose_account(
    payload: AccountIn, client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_admin)], db: Annotated[Session, Depends(get_db)],
) -> dict:
    cid = google_ads.digits(payload.customer_id)
    if payload.customer_id and len(cid) != 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A Google Ads account ID has 10 digits, like 183-526-2013.")
    client.google_ads_customer_id = cid or None
    client.google_ads_last_error = None
    db.commit()
    return {"customer_id": client.google_ads_customer_id}


@router.post("/pull")
def pull_now(client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_admin)], db: Annotated[Session, Depends(get_db)]) -> dict:
    """Pull this client's Google Ads numbers now, instead of waiting for the daily run."""
    try:
        return ads_pull.pull(db, client)
    except google_ads.GoogleAdsError as exc:
        db.rollback()
        client.google_ads_last_error = str(exc)[:500]
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
