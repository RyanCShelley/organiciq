"""Ads Accelerator for v2: how a client's Google Ads did in a month."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.services import ads_report

router = APIRouter(prefix="/v2/ads", tags=["v2 ads accelerator"])

MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
Month = Annotated[str, Query(pattern=MONTH.pattern)]


@router.get("")
def ads_report_for_month(client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_staff)], db: Annotated[Session, Depends(get_db)], month: Month) -> dict:
    return ads_report.report(db, client, month)


@router.get("/summary")
def ads_summary_for_month(client: Annotated[Client, Depends(require_client)], _: Annotated[AuthUser, Depends(require_sma_staff)], db: Annotated[Session, Depends(get_db)], month: Month) -> dict:
    return ads_report.summary(db, client, month)
