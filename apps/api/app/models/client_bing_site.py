"""A client's Bing Webmaster site.

Kept apart from `integrations` on purpose: the live tool reads that table with a
fixed list of providers, and a row it does not know would break it while both
tools share a database.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ClientBingSite(Base):
    __tablename__ = "client_bing_sites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, unique=True
    )
    site_url: Mapped[str] = mapped_column(Text, nullable=False)
    #: connected (Bing lists it, verified) | error (Bing says otherwise) | unchecked (no API key here)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
