import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ClientStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ONBOARDING = "onboarding"
    ARCHIVED = "archived"


class Tier(Base):
    __tablename__ = "tiers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    tracked_keyword_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tracked_prompt_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_allowance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    update_allowance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    growth_action_allowance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conversion_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reporting_level: Mapped[str] = mapped_column(String(50), nullable=False, default="standard")
    # monthly | bi_weekly | weekly — Watch List keyword/prompt check frequency
    watchlist_cadence: Mapped[str] = mapped_column(String(32), nullable=False, default="monthly")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    clients: Mapped[list["Client"]] = relationship(back_populates="tier")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    tier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tiers.id"), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_market: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/New_York")
    monthly_lead_goal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_sheet_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Enterprise (and optional overrides): agreement-specific plan amounts
    custom_tracked_keyword_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_tracked_prompt_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_content_allowance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_update_allowance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_growth_action_allowance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_watchlist_cadence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Dashboard baseline snapshot (calculator / contract start)
    baseline_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    # The window the snapshot was measured over. Previously only the end date
    # (baseline_as_of) was kept and the start survived as free text in notes.
    baseline_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_monthly_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    baseline_monthly_leads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    baseline_lead_rate_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    baseline_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    baseline_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ClientStatus] = mapped_column(
        Enum(ClientStatus, name="client_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ClientStatus.ONBOARDING,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tier: Mapped[Tier] = relationship(back_populates="clients")
