"""Inlink suggester for v2."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.models.schema_tools import InlinkState
from app.services import inlinks
from app.services.page_diagnostic import PageUnreadable

router = APIRouter(prefix="/v2/inlinks", tags=["v2 inlink suggester"])


@router.get("")
def inlink_suggestions(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=200, description="Find a page by address, title, or a search it ranks for")] = None,
) -> dict:
    """Pages that deserve more links, each with the pages that should link to it and the anchor text to use. `data` is null when the site was not crawled."""
    return {"data": inlinks.build(db, client, q)}


class VerifyIn(BaseModel):
    source: str = Field(min_length=8, max_length=2048)
    target: str = Field(min_length=8, max_length=2048)


@router.post("/verify")
def verify_link(
    payload: VerifyIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Read the source page now and say whether it links to the target. A link found is recorded, so it is not suggested again."""
    try:
        return inlinks.verify(db, client, payload.source, payload.target, user.email)
    except PageUnreadable as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


class StateIn(BaseModel):
    source: str = Field(min_length=8, max_length=2048)
    target: str = Field(min_length=8, max_length=2048)
    #: todo, added or skipped. "live" is set only by the live check, never by hand.
    status: Literal["todo", "added", "skipped"] | None = None
    #: The link text chosen for this link.
    anchor: str | None = Field(default=None, max_length=300)


@router.post("/state")
def set_link_state(
    payload: StateIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Save what was done with one suggested link, or the link text chosen for it."""
    return inlinks.set_state(db, client, payload.source, payload.target, user.email, payload.status, payload.anchor)


class SentenceIn(BaseModel):
    source: str = Field(min_length=8, max_length=2048)
    target: str = Field(min_length=8, max_length=2048)
    #: The link text the sentence is written around.
    anchor: str = Field(min_length=2, max_length=300)


@router.post("/sentence")
def write_link_sentence(
    payload: SentenceIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Write the sentence that carries this link, to add after the suggested paragraph. Kept on the link for the whole team."""
    return inlinks.write_sentence(db, client, payload.source, payload.target, payload.anchor, user.email)


class IgnoreIn(BaseModel):
    target: str = Field(min_length=8, max_length=2048)
    #: Leave out to ignore every suggestion for the target page.
    source: str | None = Field(default=None, max_length=2048)


@router.post("/ignore")
def ignore(
    payload: IgnoreIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    source = payload.source or ""
    row = db.query(InlinkState).filter(InlinkState.client_id == client.id, InlinkState.source_url == source, InlinkState.target_url == payload.target).one_or_none()
    if row is None:
        row = InlinkState(client_id=client.id, source_url=source, target_url=payload.target, status="ignored", created_by=user.email)
        db.add(row)
    else:
        row.status = "ignored"
    db.commit()
    return {"id": str(row.id)}


@router.delete("/ignore/{state_id}")
def restore(
    state_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    row = db.query(InlinkState).filter(InlinkState.id == state_id, InlinkState.client_id == client.id, InlinkState.status == "ignored").one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That is not ignored for this client.")
    db.delete(row)
    db.commit()
    return {"ok": True}
