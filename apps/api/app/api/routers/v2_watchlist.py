"""The v2 watchlist: buckets and their keywords, filled from a CSV.

Separate from `/watch-list`, which is the current tool's read-only view over
SE Ranking's tracked keywords.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
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
    WatchlistKeywordAddRequest,
    WatchlistKeywordAddResponse,
    WatchlistKeywordOut,
    WatchlistOut,
)
from app.services.review_visibility import key_of
from app.services.watchlist_import import import_watchlist

router = APIRouter(prefix="/v2/watchlist", tags=["v2 watchlist"])


@router.get("", response_model=WatchlistOut)
def get_watchlist(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
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


@router.post("/keywords", response_model=WatchlistKeywordAddResponse)
def add_watchlist_keyword(
    payload: WatchlistKeywordAddRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> WatchlistKeywordAddResponse:
    kw_key = key_of(payload.keyword)

    requested_bucket: WatchlistBucket | None = None
    if payload.bucket_id is not None:
        requested_bucket = (
            db.query(WatchlistBucket)
            .filter(WatchlistBucket.id == payload.bucket_id, WatchlistBucket.client_id == client.id)
            .one_or_none()
        )
        if requested_bucket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That bucket is not on this client's watchlist.",
            )

    existing = (
        db.query(WatchlistKeyword)
        .filter(WatchlistKeyword.client_id == client.id, WatchlistKeyword.keyword_key == kw_key)
        .one_or_none()
    )
    if existing is not None:
        existing_bucket = db.get(WatchlistBucket, existing.bucket_id)
        return WatchlistKeywordAddResponse(
            id=existing.id,
            keyword=existing.keyword,
            keyword_key=existing.keyword_key,
            bucket_id=existing.bucket_id,
            bucket_name=existing_bucket.name if existing_bucket else "General",
            created=False,
            bucket_created=False,
        )

    bucket_created = False
    bucket = requested_bucket
    if bucket is None and payload.bucket_name:
        b_key = key_of(payload.bucket_name)
        bucket = (
            db.query(WatchlistBucket)
            .filter(WatchlistBucket.client_id == client.id, WatchlistBucket.name_key == b_key)
            .one_or_none()
        )
        if bucket is None:
            max_order = (
                db.query(func.max(WatchlistBucket.sort_order))
                .filter(WatchlistBucket.client_id == client.id)
                .scalar()
            )
            next_order = (-1 if max_order is None else max_order) + 1
            bucket = WatchlistBucket(
                client_id=client.id,
                name=payload.bucket_name,
                name_key=b_key,
                sort_order=next_order,
            )
            db.add(bucket)
            db.flush()
            bucket_created = True
    elif bucket is None:
        bucket = (
            db.query(WatchlistBucket)
            .filter(WatchlistBucket.client_id == client.id)
            .order_by(WatchlistBucket.sort_order, WatchlistBucket.name)
            .first()
        )
        if bucket is None:
            bucket = WatchlistBucket(
                client_id=client.id,
                name="General",
                name_key="general",
                sort_order=0,
            )
            db.add(bucket)
            db.flush()
            bucket_created = True

    row = WatchlistKeyword(
        client_id=client.id,
        bucket_id=bucket.id,
        keyword=payload.keyword,
        keyword_key=kw_key,
        notes=payload.notes,
        source="manual",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return WatchlistKeywordAddResponse(
        id=row.id,
        keyword=row.keyword,
        keyword_key=row.keyword_key,
        bucket_id=bucket.id,
        bucket_name=bucket.name,
        created=True,
        bucket_created=bucket_created,
    )
