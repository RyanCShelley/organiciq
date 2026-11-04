"""A monthly review, worked out once and kept.

The review of a finished month does not change, so it is built the first time it is wanted with the data complete and
then read back. Re-running is an explicit act (it replaces this row), for when a connection or the data was wrong.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MonthlyReviewSnapshot(Base):
    __tablename__ = "monthly_review_snapshots"
    __table_args__ = (UniqueConstraint("client_id", "month", name="uq_monthly_review_snapshot"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    #: The newest Search Console and GA4 days the review was built from, so a locked month says what it saw.
    data_through: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
