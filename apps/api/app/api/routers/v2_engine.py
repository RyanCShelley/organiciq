"""The v2 Decision Engine: candidate lists for the focus a client is working on."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.decisions import visibility_candidates
from app.models.client import Client
from app.services.monthly_review import last_complete_month, parse_month

router = APIRouter(prefix="/v2/engine", tags=["v2 engine"])


@router.get("/visibility")
def visibility_candidates_for(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[str | None, Query(description="The last of the three months to read, YYYY-MM")] = None,
    bucket_id: UUID | None = None,
) -> dict:
    chosen = month or last_complete_month()
    try:
        parse_month(chosen)
        return visibility_candidates.build(db, client, chosen, bucket_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/visibility/buckets")
def visibility_bucket_overview(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[str | None, Query()] = None,
) -> list[dict]:
    """How much each watchlist bucket has to move, side by side."""
    chosen = month or last_complete_month()
    try:
        parse_month(chosen)
        return visibility_candidates.bucket_overview(db, client, chosen)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
