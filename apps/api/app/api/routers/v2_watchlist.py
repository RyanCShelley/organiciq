"""The v2 watchlist: buckets and their keywords, filled from a CSV.

Separate from `/watch-list`, which is the current tool's read-only view over
SE Ranking's tracked keywords.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.models.client_focus import ClientFocus
from app.models.gsc import FactGscQueryPage
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.schemas.v2_watchlist import (
    INT4_MAX,
    WatchlistBucketCreateRequest,
    WatchlistBucketDeleteResponse,
    WatchlistBucketOut,
    WatchlistBucketUpdateRequest,
    WatchlistImportRequest,
    WatchlistImportResponse,
    WatchlistKeywordAddRequest,
    WatchlistKeywordAddResponse,
    WatchlistKeywordBulkAddRequest,
    WatchlistKeywordBulkAddResponse,
    WatchlistKeywordDetailOut,
    WatchlistKeywordOut,
    WatchlistKeywordUpdateRequest,
    WatchlistOut,
    WatchlistSuggestionOut,
    WatchlistSuggestionsOut,
)
from app.services.review_visibility import key_of
from app.services.search_visibility import gsc_keyword_suggestions, previous_range
from app.services.watchlist_import import import_watchlist

router = APIRouter(prefix="/v2/watchlist", tags=["v2 watchlist"])


def _keyword_out(row: WatchlistKeyword) -> WatchlistKeywordOut:
    return WatchlistKeywordOut(
        id=row.id,
        keyword=row.keyword,
        volume=row.volume,
        difficulty=row.difficulty,
        intent=row.intent,
        paired_ai_prompt=row.paired_ai_prompt,
        notes=row.notes,
    )


def _get_client_bucket(db: Session, client_id: UUID, bucket_id: UUID) -> WatchlistBucket:
    bucket = (
        db.query(WatchlistBucket)
        .filter(WatchlistBucket.id == bucket_id, WatchlistBucket.client_id == client_id)
        .one_or_none()
    )
    if bucket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That bucket is not on this client's watchlist.",
        )
    return bucket


def _get_client_keyword(db: Session, client_id: UUID, keyword_id: UUID) -> WatchlistKeyword:
    row = (
        db.query(WatchlistKeyword)
        .filter(WatchlistKeyword.id == keyword_id, WatchlistKeyword.client_id == client_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That keyword is not on this client's watchlist.",
        )
    return row


def _resolve_or_create_named_bucket(
    db: Session, client_id: UUID, bucket_name: str
) -> tuple[WatchlistBucket, bool]:
    b_key = key_of(bucket_name)
    bucket = (
        db.query(WatchlistBucket)
        .filter(WatchlistBucket.client_id == client_id, WatchlistBucket.name_key == b_key)
        .one_or_none()
    )
    if bucket is not None:
        return bucket, False
    max_order = (
        db.query(func.max(WatchlistBucket.sort_order))
        .filter(WatchlistBucket.client_id == client_id)
        .scalar()
    )
    next_order = min((-1 if max_order is None else max_order) + 1, INT4_MAX)
    try:
        with db.begin_nested():
            bucket = WatchlistBucket(
                client_id=client_id,
                name=bucket_name,
                name_key=b_key,
                sort_order=next_order,
            )
            db.add(bucket)
            db.flush()
        return bucket, True
    except IntegrityError:
        winner = (
            db.query(WatchlistBucket)
            .filter(WatchlistBucket.client_id == client_id, WatchlistBucket.name_key == b_key)
            .one_or_none()
        )
        if winner is not None:
            return winner, False
        raise


def _resolve_or_create_default_bucket(
    db: Session, client_id: UUID
) -> tuple[WatchlistBucket, bool]:
    bucket = (
        db.query(WatchlistBucket)
        .filter(WatchlistBucket.client_id == client_id)
        .order_by(WatchlistBucket.sort_order, WatchlistBucket.name)
        .first()
    )
    if bucket is not None:
        return bucket, False
    try:
        with db.begin_nested():
            bucket = WatchlistBucket(
                client_id=client_id,
                name="General",
                name_key="general",
                sort_order=0,
            )
            db.add(bucket)
            db.flush()
        return bucket, True
    except IntegrityError:
        winner = (
            db.query(WatchlistBucket)
            .filter(WatchlistBucket.client_id == client_id, WatchlistBucket.name_key == "general")
            .one_or_none()
        )
        if winner is not None:
            return winner, False
        raise


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
        by_bucket.setdefault(row.bucket_id, []).append(_keyword_out(row))
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
    except (ValueError, OverflowError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concurrent watchlist import conflicted; please retry.",
        ) from exc
    except DataError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Watchlist CSV contains invalid data.",
        ) from exc
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
        requested_bucket = _get_client_bucket(db, client.id, payload.bucket_id)

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

    try:
        bucket_created = False
        bucket = requested_bucket
        if bucket is None and payload.bucket_name:
            bucket, bucket_created = _resolve_or_create_named_bucket(
                db, client.id, payload.bucket_name
            )
        elif bucket is None:
            bucket, bucket_created = _resolve_or_create_default_bucket(db, client.id)

        row = WatchlistKeyword(
            client_id=client.id,
            bucket_id=bucket.id,
            keyword=payload.keyword,
            keyword_key=kw_key,
            volume=payload.volume,
            difficulty=payload.difficulty,
            intent=payload.intent,
            paired_ai_prompt=payload.paired_ai_prompt,
            notes=payload.notes,
            source="manual",
        )
        db.add(row)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A keyword or bucket with that name already exists on this client's watchlist.",
        ) from exc
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


@router.post("/keywords/bulk", response_model=WatchlistKeywordBulkAddResponse)
def bulk_add_watchlist_keywords(
    payload: WatchlistKeywordBulkAddRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> WatchlistKeywordBulkAddResponse:
    bucket_by_id: dict[UUID, WatchlistBucket] = {
        b.id: b
        for b in db.query(WatchlistBucket).filter(WatchlistBucket.client_id == client.id).all()
    }
    bucket_by_key: dict[str, WatchlistBucket] = {b.name_key: b for b in bucket_by_id.values()}

    for item in payload.items:
        if item.bucket_id is not None and item.bucket_id not in bucket_by_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That bucket is not on this client's watchlist.",
            )

    existing_rows = (
        db.query(WatchlistKeyword).filter(WatchlistKeyword.client_id == client.id).all()
    )
    existing_by_key: dict[str, WatchlistKeyword] = {r.keyword_key: r for r in existing_rows}

    next_order = min(
        max((b.sort_order for b in bucket_by_id.values()), default=-1) + 1,
        INT4_MAX,
    )

    results: list[WatchlistKeywordAddResponse] = []
    created_bucket_ids: set[UUID] = set()
    created_count = 0
    existing_count = 0

    for item in payload.items:
        kw_key = key_of(item.keyword)
        existing = existing_by_key.get(kw_key)
        if existing is not None:
            b = bucket_by_id.get(existing.bucket_id) or db.get(
                WatchlistBucket, existing.bucket_id
            )
            if b is not None:
                bucket_by_id[b.id] = b
                bucket_by_key[b.name_key] = b
            results.append(
                WatchlistKeywordAddResponse(
                    id=existing.id,
                    keyword=existing.keyword,
                    keyword_key=existing.keyword_key,
                    bucket_id=existing.bucket_id,
                    bucket_name=b.name if b else "General",
                    created=False,
                    bucket_created=False,
                )
            )
            existing_count += 1
            continue

        if item.bucket_id is not None:
            bucket = bucket_by_id[item.bucket_id]
        elif item.bucket_name:
            b_key = key_of(item.bucket_name)
            bucket = bucket_by_key.get(b_key)
            if bucket is None:
                try:
                    with db.begin_nested():
                        candidate_bucket = WatchlistBucket(
                            client_id=client.id,
                            name=item.bucket_name,
                            name_key=b_key,
                            sort_order=next_order,
                        )
                        db.add(candidate_bucket)
                        db.flush()
                    bucket = candidate_bucket
                    next_order = min(next_order + 1, INT4_MAX)
                    bucket_by_id[bucket.id] = bucket
                    bucket_by_key[bucket.name_key] = bucket
                    created_bucket_ids.add(bucket.id)
                except IntegrityError as exc:
                    winner_bucket = (
                        db.query(WatchlistBucket)
                        .filter(
                            WatchlistBucket.client_id == client.id,
                            WatchlistBucket.name_key == b_key,
                        )
                        .one_or_none()
                    )
                    if winner_bucket is None:
                        db.rollback()
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="A bucket with that name already exists on this client's watchlist.",
                        ) from exc
                    bucket = winner_bucket
                    bucket_by_id[bucket.id] = bucket
                    bucket_by_key[bucket.name_key] = bucket
        else:
            if bucket_by_id:
                bucket = min(bucket_by_id.values(), key=lambda b: (b.sort_order, b.name))
            else:
                try:
                    with db.begin_nested():
                        candidate_bucket = WatchlistBucket(
                            client_id=client.id,
                            name="General",
                            name_key="general",
                            sort_order=0,
                        )
                        db.add(candidate_bucket)
                        db.flush()
                    bucket = candidate_bucket
                    next_order = min(max(next_order, 1), INT4_MAX)
                    bucket_by_id[bucket.id] = bucket
                    bucket_by_key[bucket.name_key] = bucket
                    created_bucket_ids.add(bucket.id)
                except IntegrityError as exc:
                    winner_bucket = (
                        db.query(WatchlistBucket)
                        .filter(
                            WatchlistBucket.client_id == client.id,
                            WatchlistBucket.name_key == "general",
                        )
                        .one_or_none()
                    )
                    if winner_bucket is None:
                        db.rollback()
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="A bucket with that name already exists on this client's watchlist.",
                        ) from exc
                    bucket = winner_bucket
                    bucket_by_id[bucket.id] = bucket
                    bucket_by_key[bucket.name_key] = bucket

        try:
            with db.begin_nested():
                candidate_row = WatchlistKeyword(
                    client_id=client.id,
                    bucket_id=bucket.id,
                    keyword=item.keyword,
                    keyword_key=kw_key,
                    volume=item.volume,
                    difficulty=item.difficulty,
                    intent=item.intent,
                    paired_ai_prompt=item.paired_ai_prompt,
                    notes=item.notes,
                    source="manual",
                )
                db.add(candidate_row)
                db.flush()
            existing_by_key[kw_key] = candidate_row
            bucket_created = bucket.id in created_bucket_ids
            if bucket_created:
                created_bucket_ids.remove(bucket.id)
            results.append(
                WatchlistKeywordAddResponse(
                    id=candidate_row.id,
                    keyword=candidate_row.keyword,
                    keyword_key=candidate_row.keyword_key,
                    bucket_id=bucket.id,
                    bucket_name=bucket.name,
                    created=True,
                    bucket_created=bucket_created,
                )
            )
            created_count += 1
        except IntegrityError as exc:
            winner_kw = (
                db.query(WatchlistKeyword)
                .filter(
                    WatchlistKeyword.client_id == client.id,
                    WatchlistKeyword.keyword_key == kw_key,
                )
                .one_or_none()
            )
            if winner_kw is None:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A keyword or bucket with that name already exists on this client's watchlist.",
                ) from exc
            existing_by_key[kw_key] = winner_kw
            winner_kw_bucket = bucket_by_id.get(winner_kw.bucket_id) or db.get(
                WatchlistBucket, winner_kw.bucket_id
            )
            if winner_kw_bucket is not None:
                bucket_by_id[winner_kw_bucket.id] = winner_kw_bucket
                bucket_by_key[winner_kw_bucket.name_key] = winner_kw_bucket
            results.append(
                WatchlistKeywordAddResponse(
                    id=winner_kw.id,
                    keyword=winner_kw.keyword,
                    keyword_key=winner_kw.keyword_key,
                    bucket_id=winner_kw.bucket_id,
                    bucket_name=winner_kw_bucket.name if winner_kw_bucket else "General",
                    created=False,
                    bucket_created=False,
                )
            )
            existing_count += 1

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A keyword or bucket with that name already exists on this client's watchlist.",
        ) from exc
    return WatchlistKeywordBulkAddResponse(
        results=results,
        created_count=created_count,
        existing_count=existing_count,
    )


@router.patch("/keywords/{keyword_id}", response_model=WatchlistKeywordDetailOut)
def update_watchlist_keyword(
    keyword_id: UUID,
    payload: WatchlistKeywordUpdateRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> WatchlistKeywordDetailOut:
    row = _get_client_keyword(db, client.id, keyword_id)
    fields = payload.model_fields_set

    if "keyword" in fields and payload.keyword is not None:
        new_key = key_of(payload.keyword)
        conflict = (
            db.query(WatchlistKeyword.id)
            .filter(
                WatchlistKeyword.client_id == client.id,
                WatchlistKeyword.keyword_key == new_key,
                WatchlistKeyword.id != row.id,
            )
            .first()
        )
        if conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A keyword matching that term is already on this client's watchlist.",
            )
        row.keyword = payload.keyword
        row.keyword_key = new_key

    try:
        if "bucket_id" in fields and payload.bucket_id is not None:
            bucket = _get_client_bucket(db, client.id, payload.bucket_id)
            row.bucket_id = bucket.id
        elif "bucket_name" in fields and payload.bucket_name is not None:
            bucket, _ = _resolve_or_create_named_bucket(db, client.id, payload.bucket_name)
            row.bucket_id = bucket.id
        else:
            bucket = _get_client_bucket(db, client.id, row.bucket_id)

        for attr in ("volume", "difficulty", "intent", "paired_ai_prompt", "notes"):
            if attr in fields:
                setattr(row, attr, getattr(payload, attr))

        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A keyword matching that term is already on this client's watchlist.",
        ) from exc
    db.refresh(row)
    return WatchlistKeywordDetailOut(
        id=row.id,
        keyword=row.keyword,
        volume=row.volume,
        difficulty=row.difficulty,
        intent=row.intent,
        paired_ai_prompt=row.paired_ai_prompt,
        notes=row.notes,
        bucket_id=row.bucket_id,
        bucket_name=bucket.name,
        source=row.source,
    )


@router.delete(
    "/keywords/{keyword_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_watchlist_keyword(
    keyword_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    row = _get_client_keyword(db, client.id, keyword_id)
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/buckets", response_model=WatchlistBucketOut, status_code=status.HTTP_201_CREATED)
def create_watchlist_bucket(
    payload: WatchlistBucketCreateRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> WatchlistBucketOut:
    b_key = key_of(payload.name)
    conflict = (
        db.query(WatchlistBucket.id)
        .filter(WatchlistBucket.client_id == client.id, WatchlistBucket.name_key == b_key)
        .first()
    )
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A bucket with that name already exists on this client's watchlist.",
        )

    if payload.sort_order is not None:
        sort_order = payload.sort_order
    else:
        max_order = (
            db.query(func.max(WatchlistBucket.sort_order))
            .filter(WatchlistBucket.client_id == client.id)
            .scalar()
        )
        sort_order = min((-1 if max_order is None else max_order) + 1, INT4_MAX)

    bucket = WatchlistBucket(
        client_id=client.id,
        name=payload.name,
        name_key=b_key,
        sort_order=sort_order,
    )
    db.add(bucket)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A bucket with that name already exists on this client's watchlist.",
        ) from exc
    db.refresh(bucket)
    return WatchlistBucketOut(
        id=bucket.id,
        name=bucket.name,
        sort_order=bucket.sort_order,
        keywords=[],
    )


@router.patch("/buckets/{bucket_id}", response_model=WatchlistBucketOut)
def update_watchlist_bucket(
    bucket_id: UUID,
    payload: WatchlistBucketUpdateRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> WatchlistBucketOut:
    bucket = _get_client_bucket(db, client.id, bucket_id)
    fields = payload.model_fields_set

    if "name" in fields and payload.name is not None:
        new_key = key_of(payload.name)
        conflict = (
            db.query(WatchlistBucket.id)
            .filter(
                WatchlistBucket.client_id == client.id,
                WatchlistBucket.name_key == new_key,
                WatchlistBucket.id != bucket.id,
            )
            .first()
        )
        if conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A bucket with that name already exists on this client's watchlist.",
            )
        bucket.name = payload.name
        bucket.name_key = new_key

    if "sort_order" in fields and payload.sort_order is not None:
        bucket.sort_order = payload.sort_order

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A bucket with that name already exists on this client's watchlist.",
        ) from exc
    db.refresh(bucket)
    keywords = (
        db.query(WatchlistKeyword)
        .filter(WatchlistKeyword.client_id == client.id, WatchlistKeyword.bucket_id == bucket.id)
        .order_by(WatchlistKeyword.volume.desc().nulls_last(), WatchlistKeyword.keyword)
        .all()
    )
    return WatchlistBucketOut(
        id=bucket.id,
        name=bucket.name,
        sort_order=bucket.sort_order,
        keywords=[_keyword_out(k) for k in keywords],
    )


@router.delete("/buckets/{bucket_id}", response_model=WatchlistBucketDeleteResponse)
def delete_watchlist_bucket(
    bucket_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    confirm: Annotated[bool, Query()] = False,
) -> WatchlistBucketDeleteResponse:
    bucket = _get_client_bucket(db, client.id, bucket_id)
    kw_count = (
        db.query(func.count(WatchlistKeyword.id))
        .filter(WatchlistKeyword.bucket_id == bucket.id)
        .scalar()
        or 0
    )
    focus_count = (
        db.query(func.count(ClientFocus.id))
        .filter(ClientFocus.bucket_id == bucket.id)
        .scalar()
        or 0
    )
    if kw_count > 0 and not confirm:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Bucket '{bucket.name}' contains {kw_count} keyword(s); pass confirm=true to delete it.",
        )

    db.delete(bucket)
    db.commit()
    return WatchlistBucketDeleteResponse(
        deleted=True,
        id=bucket.id,
        deleted_keywords=int(kw_count),
        cleared_focuses=int(focus_count),
    )


@router.get("/suggestions", response_model=WatchlistSuggestionsOut)
def get_watchlist_suggestions(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=365)] = 90,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=200)] = None,
) -> WatchlistSuggestionsOut:
    if search is not None and "\x00" in search:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Search query cannot contain NUL characters.",
        )
    gsc_row = (
        db.query(Integration)
        .filter(
            Integration.client_id == client.id,
            Integration.provider == IntegrationProvider.GSC,
        )
        .one_or_none()
    )
    gsc_connected = bool(
        gsc_row is not None
        and gsc_row.connection_status == ConnectionStatus.CONNECTED
        and (gsc_row.external_property_id or "").strip()
    )
    google_through = (
        db.query(func.max(FactGscQueryPage.date))
        .filter(FactGscQueryPage.client_id == client.id)
        .scalar()
    )
    if google_through is None:
        return WatchlistSuggestionsOut(
            gsc_connected=gsc_connected,
            has_gsc_data=False,
            google_through=None,
            days=days,
            suggestions=[],
        )

    end = google_through
    start = end - timedelta(days=days - 1)
    ps, pe = previous_range(start, end)
    rows = gsc_keyword_suggestions(
        db,
        client,
        start,
        end,
        ps,
        pe,
        limit=limit,
        search=search,
        strict=not bool((search or "").strip()),
    )
    return WatchlistSuggestionsOut(
        gsc_connected=gsc_connected,
        has_gsc_data=True,
        google_through=google_through.isoformat(),
        days=days,
        suggestions=[WatchlistSuggestionOut(**item) for item in rows],
    )
