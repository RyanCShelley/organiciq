"""The v2 watchlist: buckets and their keywords, filled from a CSV.

Separate from `/watch-list`, which is the current tool's read-only view over
SE Ranking's tracked keywords.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.schemas.v2_watchlist import (
    WatchlistBucketOut,
    WatchlistImportRequest,
    WatchlistImportResponse,
    WatchlistKeywordOut,
    WatchlistOut,
)
from app.services.watchlist_import import import_watchlist

router = APIRouter(prefix="/v2/watchlist", tags=["v2 watchlist"])


@router.get("", response_model=WatchlistOut)
def get_watchlist(
    client: Annotated[Client, Depends(require_client)],
    db: Annotated[Session, Depends(get_db)],
) -> WatchlistOut:
    buckets = (
        db.query(WatchlistBucket)
        .filter(WatchlistBucket.client_id == client.id)
        .order_by(WatchlistBucket.sort_order, WatchlistBucket.name)
        .all()
    )
    keywords = (
        db.query(WatchlistKeyword)
        .filter(WatchlistKeyword.client_id == client.id)
        .order_by(WatchlistKeyword.volume.desc().nulls_last(), WatchlistKeyword.keyword)
        .all()
    )
    by_bucket: dict = {}
    for row in keywords:
        by_bucket.setdefault(row.bucket_id, []).append(
            WatchlistKeywordOut(
                id=row.id,
                keyword=row.keyword,
                volume=row.volume,
                difficulty=row.difficulty,
                intent=row.intent,
                paired_ai_prompt=row.paired_ai_prompt,
                notes=row.notes,
            )
        )
    return WatchlistOut(
        buckets=[
            WatchlistBucketOut(
                id=b.id, name=b.name, sort_order=b.sort_order, keywords=by_bucket.get(b.id, [])
            )
            for b in buckets
        ],
        keyword_count=len(keywords),
    )


@router.post("/import", response_model=WatchlistImportResponse)
def import_watchlist_csv(
    payload: WatchlistImportRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> WatchlistImportResponse:
    try:
        report = import_watchlist(db, client, payload.csv_text, dry_run=payload.dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return WatchlistImportResponse(**report)
