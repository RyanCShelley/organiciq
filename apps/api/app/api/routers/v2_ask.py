"""Ask the data: questions in plain words about one client's numbers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ask import engine, schema
from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.core.settings import get_settings
from app.models.ask_data import AskDataLog
from app.models.client import Client
from app.services import model_spend

router = APIRouter(prefix="/v2/ask", tags=["v2 ask the data"])


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1500)
    depth: Literal["quick", "deep", "deepest"] = "quick"
    #: The conversation so far, so a follow-up ("and last month?") makes sense.
    history: list[Turn] = Field(default_factory=list, max_length=12)


def _out(row: AskDataLog) -> dict:
    return {
        "id": str(row.id), "status": row.status, "question": row.question, "depth": row.depth, "model": row.model,
        "answer": row.answer, "error": row.error, "queries": row.queries or [],
        "cost_usd": float(row.cost_usd or 0), "asked_by": row.asked_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _spend(db: Session, client: Client) -> dict:
    cap = get_settings().ask_monthly_cap_usd
    used = float(model_spend.month_spend(db, client))
    return {"used_usd": round(used, 2), "cap_usd": cap, "left_usd": round(max(cap - used, 0), 2)}


@router.get("")
def recent_questions(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    rows = db.query(AskDataLog).filter(AskDataLog.client_id == client.id).order_by(AskDataLog.created_at.desc()).limit(15).all()
    return {
        "spend": _spend(db, client),
        "depths": {k: {"model": v[0]} for k, v in engine.DEPTHS.items()},
        "ready": bool(get_settings().anthropic_api_key.strip()),
        "recent": [_out(r) for r in rows],
    }


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def ask(
    payload: AskIn,
    background: BackgroundTasks,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    if not get_settings().anthropic_api_key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The Anthropic key is not set on this install, so questions cannot be answered.")
    spend = _spend(db, client)
    if spend["left_usd"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This client has used its ${spend['cap_usd']:.0f} for questions this month. The limit resets on the 1st.",
        )
    try:
        schema.ensure(db)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"The read-only door to the data could not be set up: {str(exc)[:200]}") from exc
    row = AskDataLog(client_id=client.id, asked_by=user.email, depth=payload.depth, model=engine.DEPTHS[payload.depth][0], question=payload.question.strip(), status="running", queries=[])
    db.add(row)
    db.commit()
    background.add_task(engine.answer, row.id, [t.model_dump() for t in payload.history])
    return {"id": str(row.id)}


@router.get("/{question_id}")
def question(
    question_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    row = db.query(AskDataLog).filter(AskDataLog.id == question_id, AskDataLog.client_id == client.id).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That question is not on this client.")
    if row.status == "running" and row.created_at < datetime.now(timezone.utc) - timedelta(minutes=engine.STALE_MINUTES):
        # The API restarted while it was working (a deploy), or the model never answered.
        row.status, row.error, row.completed_at = "failed", "This question was interrupted. Ask it again.", datetime.now(timezone.utc)
        db.commit()
    return {**_out(row), "spend": _spend(db, client)}
