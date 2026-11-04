"""One question asked of a client's data, with how it was worked out and what it cost."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AskDataLog(Base):
    __tablename__ = "ask_data_log"
    __table_args__ = (Index("ix_ask_data_log_client_created", "client_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    asked_by: Mapped[str] = mapped_column(String(255), nullable=False)
    #: quick, deep or deepest: which model answers.
    depth: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    #: running, done or failed.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The queries run, in order, with how many rows each returned.
    queries: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
