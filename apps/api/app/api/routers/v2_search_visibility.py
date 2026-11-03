"""Search visibility for v2: the watchlist's terms across Google, Bing and SE Ranking."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.services import google_updates, search_visibility

router = APIRouter(prefix="/v2/search-visibility", tags=["v2 search visibility"])

MAX_RANGE_DAYS = 800


def _range(start: date, end: date) -> None:
    if end < start or (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a start before the end, no more than about two years apart.")


@router.get("")
def search_visibility_report(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
    bucket: str | None = None,
) -> dict:
    _range(start, end)
    google_updates.refresh(db)
    return search_visibility.build(db, client, start, end, bucket or None)


@router.get("/term")
def search_visibility_for_term(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    term: Annotated[str, Query(min_length=1, max_length=400)],
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
) -> dict:
    _range(start, end)
    return search_visibility.term_detail(db, client, term, start, end)
