"""What GA4 shows for conversion pages, for v2's Conversions & Goals screen."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.services import ga4_conversion_pages

router = APIRouter(prefix="/v2/conversions", tags=["v2 conversions"])


@router.get("/pages")
def conversion_pages_seen_by_ga4(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    event: Annotated[list[str], Query(min_length=1, max_length=20)],
    days: Annotated[int, Query(ge=7, le=365)] = 90,
) -> list[dict]:
    """The pages each of these events fired on in the last `days` days, busiest first."""
    try:
        return ga4_conversion_pages.pages_for_events(db, client, event, days=days)
    except ga4_conversion_pages.Ga4NotReady as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"GA4 did not return the report: {exc}"
        ) from exc
