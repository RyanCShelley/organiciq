"""The consulting portal's records: what we know about the client's business, then (in later steps) recommendations, reports and their history."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ConsultingProfile(Base):
    """The Understand step: goals, audiences, constraints and the brand's editorial rules, written by the consultant. Internal: the client does not see the notes."""

    __tablename__ = "consulting_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, unique=True)
    goals: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    audiences: Mapped[str | None] = mapped_column(Text, nullable=True)
    markets: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_services: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints: Mapped[str | None] = mapped_column(Text, nullable=True)
    editorial_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    resources: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
