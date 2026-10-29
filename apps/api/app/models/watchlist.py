"""The watchlist: the terms a client is worked on, grouped into topical buckets.

A bucket is what the operator picks in the Decision Engine ("this month we are
working on SEO for SMA"). It was only ever a `group_name` string copied off SE
Ranking; here it is a row, owned by this tool and filled from the client's
account sheet or a CSV.

Each keyword carries the AI prompt paired with it, which is what LLM visibility
runs against.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WatchlistBucket(Base):
    __tablename__ = "watchlist_buckets"
    __table_args__ = (UniqueConstraint("client_id", "name_key", name="uq_watchlist_bucket_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    #: Lower-cased and whitespace-collapsed, so "SEO  for SMA" and "seo for sma" are one bucket.
    name_key: Mapped[str] = mapped_column(String(160), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WatchlistKeyword(Base):
    __tablename__ = "watchlist_keywords"
    __table_args__ = (
        UniqueConstraint("client_id", "keyword_key", name="uq_watchlist_keyword"),
        Index("ix_watchlist_keywords_bucket", "bucket_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    bucket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watchlist_buckets.id", ondelete="CASCADE"), nullable=False
    )
    keyword: Mapped[str] = mapped_column(String(400), nullable=False)
    keyword_key: Mapped[str] = mapped_column(String(400), nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    paired_ai_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Where the row came from: "csv" or "sheet".
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="csv")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
