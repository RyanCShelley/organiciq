from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.copilot.chat import run_chat
from app.copilot.gateway import Gateway, GatewayError, GatewayNotConfigured, get_gateway
from app.copilot.tools import ToolContext
from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.core.settings import get_settings
from app.models.client import Client
from app.models.copilot import CopilotConversation, CopilotMessage

logger = logging.getLogger("organiciq.copilot")

router = APIRouter(prefix="/copilot", tags=["copilot"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: UUID | None = None


class ChatOut(BaseModel):
    conversation_id: UUID
    message_id: UUID
    reply: str
    rounds: int
    #: True when the model ran out of lookups before answering.
    incomplete: bool


class RatingIn(BaseModel):
    rating: int = Field(ge=-1, le=1)
    correction: str | None = Field(default=None, max_length=4000)


def _gateway() -> Gateway:
    try:
        return get_gateway()
    except GatewayNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Copilot is not configured"
        ) from exc


def _history(db: Session, conversation_id: UUID) -> list[dict]:
    rows = (
        db.query(CopilotMessage)
        .filter(CopilotMessage.conversation_id == conversation_id)
        .order_by(CopilotMessage.seq)
        .all()
    )
    out: list[dict] = []
    for r in rows:
        msg: dict = {"role": r.role, "content": r.content}
        if r.tool_calls:
            msg["tool_calls"] = r.tool_calls
        if r.tool_call_id:
            msg["tool_call_id"] = r.tool_call_id
        out.append(msg)
    return out


@router.post("/chat", response_model=ChatOut)
def chat(
    payload: ChatIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    gateway: Annotated[Gateway, Depends(_gateway)],
) -> ChatOut:
    """Ask the copilot about the client named in the header.

    Staff only for now. A conversation belongs to one user and one client, so
    a conversation id from another client's page is a 404, not a way across.
    """
    if payload.conversation_id is None:
        convo = CopilotConversation(
            client_id=client.id, user_id=user.id, title=payload.message[:120]
        )
        db.add(convo)
        db.flush()
        history: list[dict] = []
    else:
        convo = (
            db.query(CopilotConversation)
            .filter(
                CopilotConversation.id == payload.conversation_id,
                CopilotConversation.client_id == client.id,
                CopilotConversation.user_id == user.id,
            )
            .one_or_none()
        )
        if convo is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        history = _history(db, convo.id)

    settings = get_settings()
    try:
        result = run_chat(
            ToolContext(db=db, client=client),
            gateway,
            history,
            payload.message,
            max_rounds=settings.copilot_max_tool_rounds,
        )
    except GatewayError as exc:
        db.rollback()
        logger.warning("copilot model call failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="The model could not be reached"
        ) from exc

    next_seq = (
        db.query(func.coalesce(func.max(CopilotMessage.seq), 0))
        .filter(CopilotMessage.conversation_id == convo.id)
        .scalar()
        or 0
    )
    rows: list[CopilotMessage] = []
    for msg in [{"role": "user", "content": payload.message}, *result.messages]:
        next_seq += 1
        row = CopilotMessage(
            conversation_id=convo.id,
            seq=next_seq,
            role=msg["role"],
            content=msg.get("content"),
            tool_calls=msg.get("tool_calls"),
            tool_call_id=msg.get("tool_call_id"),
            model=settings.llm_model if msg["role"] == "assistant" else None,
        )
        db.add(row)
        rows.append(row)
    db.commit()

    final = rows[-1]
    return ChatOut(
        conversation_id=convo.id,
        message_id=final.id,
        reply=result.reply,
        rounds=result.rounds,
        incomplete=result.exhausted,
    )


@router.post(
    "/messages/{message_id}/rating",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def rate_message(
    message_id: UUID,
    payload: RatingIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    row = (
        db.query(CopilotMessage)
        .join(CopilotConversation, CopilotConversation.id == CopilotMessage.conversation_id)
        .filter(
            CopilotMessage.id == message_id,
            CopilotMessage.role == "assistant",
            CopilotConversation.client_id == client.id,
            CopilotConversation.user_id == user.id,
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Message not found")
    row.rating = payload.rating or None
    row.correction = payload.correction
    db.commit()
