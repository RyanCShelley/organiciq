import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.config import OrganicChannel


class StagingGa4Traffic(Base):
    __tablename__ = "staging_ga4_traffic"
    __table_args__ = (Index("ix_staging_ga4_traffic_job", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    landing_page: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    session_medium: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sessions: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    active_users: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    views: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    engaged_sessions: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StagingGa4Event(Base):
    __tablename__ = "staging_ga4_events"
    __table_args__ = (Index("ix_staging_ga4_events_job", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    landing_page: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    session_medium: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FactGa4Traffic(Base):
    __tablename__ = "facts_ga4_traffic"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "date",
            "normalized_url",
            "channel",
            "session_source",
            "session_medium",
            name="uq_facts_ga4_traffic_grain",
        ),
        Index("ix_facts_ga4_traffic_client_date", "client_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    session_source: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    session_medium: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    channel: Mapped[OrganicChannel] = mapped_column(
        Enum(OrganicChannel, name="organic_channel", values_callable=lambda x: [e.value for e in x], create_type=False),
        nullable=False,
    )
    sessions: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    active_users: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    views: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    # NULL until a GA4 sync that includes engagedSessions — used for bounce rate.
    engaged_sessions: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FactGa4Event(Base):
    __tablename__ = "facts_ga4_events"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "date",
            "normalized_url",
            "channel",
            "session_source",
            "session_medium",
            "event_name",
            name="uq_facts_ga4_events_grain",
        ),
        Index("ix_facts_ga4_events_client_date", "client_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    session_source: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    session_medium: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    channel: Mapped[OrganicChannel] = mapped_column(
        Enum(OrganicChannel, name="organic_channel", values_callable=lambda x: [e.value for e in x], create_type=False),
        nullable=False,
    )
    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
