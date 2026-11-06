"""The monthly review: one month at a glance, for v2."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.services import month_work, monthly_review, review_scorecards

router = APIRouter(prefix="/v2/review", tags=["v2 review"])


def _with_scorecards(db: Session, client: Client, review: dict) -> dict:
    """The three scorecards and the one line, worked out now: a month that locked before they existed gets them too."""
    return {**review, "scorecards": review_scorecards.build(db, client, review), "work": month_work.build(db, client, review["month"])}


@router.get("")
def monthly_review_for(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[str | None, Query(description="YYYY-MM; defaults to the last complete month")] = None,
) -> dict:
    chosen = month or monthly_review.last_complete_month()
    try:
        return _with_scorecards(db, client, monthly_review.review_for(db, client, chosen))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/rerun")
def rerun_monthly_review(
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[str, Query(description="YYYY-MM")],
) -> dict:
    """Throw away the locked review of a month and work it out again from the data held now."""
    try:
        return _with_scorecards(db, client, monthly_review.review_for(db, client, month, rerun=True, who=user.email))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
