import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, func
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
    conversion_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reporting_level: Mapped[str] = mapped_column(String(50), nullable=False, default="standard")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    clients: Mapped[list["Client"]] = relationship(back_populates="tier")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    tier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tiers.id"), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_market: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/New_York")
    monthly_lead_goal: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
