"""Locked baselines: one row per version, never edited.

A client's `baseline_*` columns hold the current numbers for the dashboard. This
table keeps how each was made and why it changed, so a re-baseline after a relaunch
is a new version with a reason, and the old one is still there.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BaselineVersion(Base):
    __tablename__ = "baseline_versions"
    __table_args__ = (
        UniqueConstraint("client_id", "version", name="uq_baseline_versions_client_version"),
        Index("ix_baseline_versions_client", "client_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    #: initial, relaunch, tracking_change, definition_change or correction.
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_by: Mapped[str] = mapped_column(String(255), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    #: provisional when it was locked with under three months in the regime.
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    method_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(8), nullable=False)
    regime_start: Mapped[str | None] = mapped_column(String(7), nullable=True)
    window_from: Mapped[str] = mapped_column(String(7), nullable=False)
    window_to: Mapped[str] = mapped_column(String(7), nullable=False)
    lead_events: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    acknowledged: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    monthly_sessions: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    monthly_organic_sessions: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    lead_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    monthly_leads: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    #: The low end of the lead range, which the goal is built from.
    goal_monthly_leads: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    #: The whole analysis it was locked from: series, ranges, flags, projection.
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
