"""A client's feed URLs. Any staff member can read them; adding and removing is staff-only too."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.models.client_feed import ClientFeed
from app.schemas.client_feed import ClientFeedCreate, ClientFeedOut

router = APIRouter(prefix="/v2/feeds", tags=["v2 feeds"])


def _clean_url(raw: str) -> str:
    url = raw.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or " " in url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter the full feed address, starting with http:// or https://",
        )
    return url


def _key(url: str) -> str:
    return url.lower().rstrip("/")


def _out(feed: ClientFeed) -> ClientFeedOut:
    return ClientFeedOut(id=feed.id, url=feed.url, label=feed.label)


@router.get("", response_model=list[ClientFeedOut])
def list_feeds(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ClientFeedOut]:
    rows = (
        db.query(ClientFeed)
        .filter(ClientFeed.client_id == client.id)
        .order_by(ClientFeed.created_at, ClientFeed.url)
        .all()
    )
    return [_out(r) for r in rows]


@router.post("", response_model=ClientFeedOut, status_code=status.HTTP_201_CREATED)
def add_feed(
    payload: ClientFeedCreate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> ClientFeedOut:
    url = _clean_url(payload.url)
    exists = (
        db.query(ClientFeed)
        .filter(ClientFeed.client_id == client.id, ClientFeed.url_key == _key(url))
        .one_or_none()
    )
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That feed is already on this client."
        )
    feed = ClientFeed(
        client_id=client.id, url=url, url_key=_key(url), label=(payload.label or "").strip() or None
    )
    db.add(feed)
    db.commit()
    db.refresh(feed)
    return _out(feed)


@router.delete("/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_feed(
    feed_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    feed = (
        db.query(ClientFeed)
        .filter(ClientFeed.id == feed_id, ClientFeed.client_id == client.id)
        .one_or_none()
    )
    if feed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")
    db.delete(feed)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
