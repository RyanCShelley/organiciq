"""A pattern in a page address that marks a finished conversion, such as `/thank-you`.

Kept apart from `client_conversion_pages` on purpose. The engine reads those as
offers to send readers to, and a thank-you page whose address carries a one-off
order token is something to *count*, never a place to link.

A page matches when its path, lower-cased, contains the pattern.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ClientCompletionPattern(Base):
    __tablename__ = "client_completion_patterns"
    __table_args__ = (UniqueConstraint("client_id", "pattern", name="uq_client_completion_pattern"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
