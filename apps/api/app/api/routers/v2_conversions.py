"""What GA4 shows for conversion pages, for v2's Conversions & Goals screen."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.models.client_completion_pattern import ClientCompletionPattern
from app.services import ga4_conversion_pages

router = APIRouter(prefix="/v2/conversions", tags=["v2 conversions"])


class PatternIn(BaseModel):
    pattern: str
    label: str | None = None


class PatternOut(BaseModel):
    pattern: str
    label: str | None


@router.get("/pages")
def conversion_pages_seen_by_ga4(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    event: Annotated[list[str], Query(min_length=1, max_length=20)],
    days: Annotated[int, Query(ge=7, le=365)] = 90,
) -> dict:
    """The pages each of these events fired on in the last `days` days, busiest first.

    `tracked` is what the client's thank-you patterns matched, `suggested` groups the
    remaining pages whose address ends in a completion word (thank-you, order
    confirmation), and `pages` is the rest, trimmed to the busiest.
    """
    try:
        pages = ga4_conversion_pages.pages_for_events(db, client, event, days=days)
        return ga4_conversion_pages.summarise(pages)
    except ga4_conversion_pages.Ga4NotReady as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"GA4 did not return the report: {exc}"
        ) from exc


@router.get("/completion-patterns", response_model=list[PatternOut])
def list_completion_patterns(
    client: Annotated[Client, Depends(require_client)],
    db: Annotated[Session, Depends(get_db)],
) -> list[PatternOut]:
    rows = (
        db.query(ClientCompletionPattern)
        .filter(ClientCompletionPattern.client_id == client.id)
        .order_by(ClientCompletionPattern.pattern)
        .all()
    )
    return [PatternOut(pattern=r.pattern, label=r.label) for r in rows]


@router.put("/completion-patterns", response_model=list[PatternOut])
def replace_completion_patterns(
    payload: list[PatternIn],
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[PatternOut]:
    """Replace the whole list, because that is how the screen edits it."""
    if len(payload) > 20:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At most 20 patterns.")
    cleaned: dict[str, str | None] = {}
    for entry in payload:
        try:
            pattern = ga4_conversion_pages.clean_pattern(entry.pattern)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        cleaned.setdefault(pattern, (entry.label or "").strip() or None)

    db.query(ClientCompletionPattern).filter(ClientCompletionPattern.client_id == client.id).delete()
    db.add_all(
        ClientCompletionPattern(client_id=client.id, pattern=p, label=label) for p, label in cleaned.items()
    )
    db.commit()
    return list_completion_patterns(client=client, db=db)
