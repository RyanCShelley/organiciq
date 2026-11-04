"""Bing Webmaster query statistics.

Bing reports per week, not per day, so `week_start` is the first day of the week it
covers. A month sums the weeks that start in it; the edge weeks are approximate and the
screen says so.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class FactBingQueryStat(Base):
    __tablename__ = "facts_bing_query_stats"
    __table_args__ = (
        UniqueConstraint("client_id", "week_start", "query_key", name="uq_facts_bing_query_stats_grain"),
        Index("ix_facts_bing_query_stats_client_week", "client_id", "week_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    #: Lower-cased and trimmed: what a watchlist term is matched against.
    query_key: Mapped[str] = mapped_column(Text, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_impression_position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    #: Bing sends -1 when nobody clicked; stored as null.
    avg_click_position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
