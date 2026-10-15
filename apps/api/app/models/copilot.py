"""Copilot conversations.

Every message is kept, including the tool calls and their results, with the
model that produced it and the staff member's rating. That log is the training
set for fine-tuning later, so it is written from the first use.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CopilotConversation(Base):
    __tablename__ = "copilot_conversations"
    __table_args__ = (Index("ix_copilot_conversations_client_user", "client_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CopilotMessage(Base):
    __tablename__ = "copilot_messages"
    __table_args__ = (Index("ix_copilot_messages_conversation", "conversation_id", "seq"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("copilot_conversations.id", ondelete="CASCADE"), nullable=False
    )
    #: Order within the conversation. created_at ties inside one transaction.
    seq: Mapped[int] = mapped_column(nullable=False)
    #: user | assistant | tool
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The assistant's tool calls, as the model returned them.
    tool_calls: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: Which model wrote it: stock Qwen today, a fine-tune later.
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: 1 helpful, -1 not. Set by staff on a final assistant message.
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    #: What the answer should have said, when staff correct it.
    correction: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
