"""The focus a client works on in one month: what to improve, and where.

One per client per month. `month` is always the first day of the month.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

FOCUSES = ("visibility", "traffic", "leads")


class ClientFocus(Base):
    __tablename__ = "client_focuses"
    __table_args__ = (UniqueConstraint("client_id", "month", name="uq_client_focus_month"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    focus: Mapped[str] = mapped_column(String(16), nullable=False)
    bucket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watchlist_buckets.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
