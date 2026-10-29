"""The monthly focus: one per client per month, set by staff, readable by anyone with access."""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.models.client_focus import ClientFocus
from app.models.watchlist import WatchlistBucket
from app.schemas.client_focus import ClientFocusOut, ClientFocusSet

router = APIRouter(prefix="/v2/focus", tags=["v2 focus"])

_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _first_of_month(month: str) -> date:
    match = _MONTH.match(month)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Month must look like 2026-10."
        )
    return date(int(match.group(1)), int(match.group(2)), 1)


def _out(row: ClientFocus, bucket_name: str | None) -> ClientFocusOut:
    return ClientFocusOut(
        month=row.month.strftime("%Y-%m"),
        focus=row.focus,
        bucket_id=row.bucket_id,
        bucket_name=bucket_name,
    )


def _bucket_name(db: Session, bucket_id) -> str | None:
    if bucket_id is None:
        return None
    return db.query(WatchlistBucket.name).filter(WatchlistBucket.id == bucket_id).scalar()


@router.get("", response_model=list[ClientFocusOut])
def list_focuses(
    client: Annotated[Client, Depends(require_client)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ClientFocusOut]:
    """Every month this client has a focus, newest first."""
    rows = (
        db.query(ClientFocus, WatchlistBucket.name)
        .outerjoin(WatchlistBucket, WatchlistBucket.id == ClientFocus.bucket_id)
        .filter(ClientFocus.client_id == client.id)
        .order_by(ClientFocus.month.desc())
        .all()
    )
    return [_out(focus, name) for focus, name in rows]


@router.get("/{month}", response_model=ClientFocusOut | None)
def get_focus(
    month: str,
    client: Annotated[Client, Depends(require_client)],
    db: Annotated[Session, Depends(get_db)],
) -> ClientFocusOut | None:
    row = (
        db.query(ClientFocus)
        .filter(ClientFocus.client_id == client.id, ClientFocus.month == _first_of_month(month))
        .one_or_none()
    )
    return _out(row, _bucket_name(db, row.bucket_id)) if row else None


@router.put("/{month}", response_model=ClientFocusOut)
def set_focus(
    month: str,
    payload: ClientFocusSet,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> ClientFocusOut:
    first = _first_of_month(month)
    if payload.bucket_id is not None:
        own = (
            db.query(WatchlistBucket.id)
            .filter(WatchlistBucket.id == payload.bucket_id, WatchlistBucket.client_id == client.id)
            .first()
        )
        if own is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That bucket is not on this client's watchlist.",
            )
    row = (
        db.query(ClientFocus)
        .filter(ClientFocus.client_id == client.id, ClientFocus.month == first)
        .one_or_none()
    )
    if row is None:
        row = ClientFocus(client_id=client.id, month=first)
        db.add(row)
    row.focus = payload.focus
    row.bucket_id = payload.bucket_id
    db.commit()
    db.refresh(row)
    return _out(row, _bucket_name(db, row.bucket_id))


@router.delete("/{month}", status_code=status.HTTP_204_NO_CONTENT)
def clear_focus(
    month: str,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    db.query(ClientFocus).filter(
        ClientFocus.client_id == client.id, ClientFocus.month == _first_of_month(month)
    ).delete()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
