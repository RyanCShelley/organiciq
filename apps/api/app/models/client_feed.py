"""A client's feed: where the tool learns what they published, and when.

The feed gives the publish date for the content calendar; the crawl is the
cross-check. A client can have more than one (a blog and a news section, say).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ClientFeed(Base):
    __tablename__ = "client_feeds"
    __table_args__ = (
        UniqueConstraint("client_id", "url_key", name="uq_client_feed_url"),
        Index("ix_client_feeds_client", "client_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    #: Lower-cased, no trailing slash: what makes two spellings the same feed.
    url_key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
