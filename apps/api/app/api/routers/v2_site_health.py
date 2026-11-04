"""Site health for v2: SEO health and GEO readiness, by month."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.services import site_health

router = APIRouter(prefix="/v2/site-health", tags=["v2 site health"])


@router.get("")
def site_health_for_month(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[str | None, Query(description="YYYY-MM; defaults to the month of the crawl held now")] = None,
) -> dict:
    if month is not None and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Month must look like 2026-10.")
    chosen = month or site_health.default_month(db, client)
    data = site_health.for_month(db, client, chosen) if chosen else None
    return {"month": chosen, "months": site_health.months(db, client), "data": data}
