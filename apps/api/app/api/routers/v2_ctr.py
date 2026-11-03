"""CTR optimizer for v2: pages and searches earning fewer clicks than their position should."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.models.client import Client
from app.core.settings import get_settings
from app.services import ctr_optimizer, ctr_titles, model_spend

router = APIRouter(prefix="/v2/ctr", tags=["v2 ctr optimizer"])

MAX_RANGE_DAYS = 800


def _range(start: date, end: date) -> None:
    if end < start or (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a start before the end, no more than about two years apart.")


@router.get("")
def ctr_optimizer_report(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
) -> dict:
    _range(start, end)
    return ctr_optimizer.build(db, client, start, end)


@router.get("/page")
def ctr_optimizer_page(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    url: Annotated[str, Query(min_length=8, max_length=2048)],
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
) -> dict:
    _range(start, end)
    return {**ctr_optimizer.page_detail(db, client, url, start, end), "title_draft": ctr_titles.latest(db, client, url), "model_ready": bool(get_settings().anthropic_api_key.strip())}


class TitleIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    start: date = Field(alias="from")
    end: date = Field(alias="to")
    depth: Literal["quick", "deep", "deepest"] = "quick"


@router.post("/title", status_code=status.HTTP_202_ACCEPTED)
def write_title(
    payload: TitleIn,
    background: BackgroundTasks,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Have the model write title tag options for a page from its search data. A draft: nothing is sent, and no page allowance is used."""
    _range(payload.start, payload.end)
    if not get_settings().anthropic_api_key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The Anthropic key is not set on this install, so the model cannot be asked.")
    cap = get_settings().ask_monthly_cap_usd
    if float(model_spend.month_spend(db, client)) >= cap:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"This client has used its ${cap:.0f} for model questions this month. The limit resets on the 1st.")
    row = ctr_titles.start(db, client, payload.url, payload.depth, payload.start, payload.end, user.email)
    background.add_task(ctr_titles.run, row.id)
    return {"id": str(row.id)}
