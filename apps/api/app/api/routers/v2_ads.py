"""Ads Accelerator for v2: how a client's Google Ads did in a month."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_admin, require_sma_staff
from app.models.ads import ClientAdsAccount
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


def _account_out(a: ClientAdsAccount) -> dict:
    return {"customer_id": a.customer_id, "name": a.name, "kind": a.kind, "last_pull_at": a.last_pull_at.isoformat() if a.last_pull_at else None, "last_error": a.last_error}


@router.get("/connection")
def connection(client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_staff)], db: Annotated[Session, Depends(get_db)]) -> dict:
    """Where the Google Ads connection stands for this client: the permission, and each account chosen with how its last pull went."""
    return {
        "enabled": ads_report.enabled(client), "permission": google_ads.permission_granted(db), "manager_set": bool(google_ads.digits(get_settings().google_ads_login_customer_id)),
        "accounts": [_account_out(a) for a in ads_pull.accounts_of(db, client)],
    }


@router.get("/available")
def available(_: Annotated[AuthUser, Depends(require_sma_admin)], db: Annotated[Session, Depends(get_db)]) -> dict:
    """The client accounts under the manager account, to choose from."""
    try:
        return {"accounts": google_ads.list_accounts(google_ads.access_token(db))}
    except google_ads.GoogleAdsError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


class AccountIn(BaseModel):
    customer_id: str = Field(min_length=1, max_length=30, description="Digits; dashes allowed.")
    name: str = Field(default="", max_length=255)
    kind: Literal["ads", "lsa"] = "ads"


@router.post("/accounts")
def add_account(
    payload: AccountIn, client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_admin)], db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Add a Google Ads account to this client. A client can have several: search ads, Local Services Ads, and so on."""
    cid = google_ads.digits(payload.customer_id)
    if len(cid) != 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A Google Ads account ID has 10 digits, like 183-526-2013.")
    row = db.query(ClientAdsAccount).filter(ClientAdsAccount.client_id == client.id, ClientAdsAccount.customer_id == cid).one_or_none()
    if row is None:
        row = ClientAdsAccount(client_id=client.id, customer_id=cid, name=payload.name.strip(), kind=payload.kind)
        db.add(row)
    else:
        row.name, row.kind, row.last_error = payload.name.strip() or row.name, payload.kind, None
    db.commit()
    return _account_out(row)


@router.delete("/accounts/{customer_id}")
def remove_account(customer_id: str, client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_admin)], db: Annotated[Session, Depends(get_db)]) -> dict:
    """Take an account off this client. Numbers already pulled from it are kept until the next pull of the others replaces their windows."""
    row = db.query(ClientAdsAccount).filter(ClientAdsAccount.client_id == client.id, ClientAdsAccount.customer_id == google_ads.digits(customer_id)).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That account is not on this client.")
    db.delete(row)
    db.commit()
    return {"deleted": True}


@router.post("/pull")
def pull_now(client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_admin)], db: Annotated[Session, Depends(get_db)]) -> dict:
    """Pull every Google Ads account this client has now, instead of waiting for the daily run."""
    try:
        return ads_pull.pull(db, client)
    except google_ads.GoogleAdsError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
