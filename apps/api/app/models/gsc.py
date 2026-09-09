import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StagingGscDaily(Base):
    __tablename__ = "staging_gsc_daily"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gsc_site_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    impressions: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    clicks: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    ctr: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    average_position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StagingGscPage(Base):
    __tablename__ = "staging_gsc_pages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    page: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(String(16), nullable=True)
    device: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gsc_site_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    impressions: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    clicks: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    ctr: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    average_position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StagingGscQueryPage(Base):
    __tablename__ = "staging_gsc_query_pages"
    __table_args__ = (
        CheckConstraint(
            "query IS NULL OR length(trim(query)) > 0",
            name="ck_staging_gsc_query_pages_query_nonblank",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    page: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(String(16), nullable=True)
    device: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gsc_site_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    impressions: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    clicks: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    ctr: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    average_position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FactGscDaily(Base):
    __tablename__ = "facts_gsc_daily"
    __table_args__ = (
        UniqueConstraint("client_id", "date", name="uq_facts_gsc_daily_grain"),
        Index("ix_facts_gsc_daily_client_date", "client_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    impressions: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    clicks: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    ctr: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    average_position: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FactGscPage(Base):
    __tablename__ = "facts_gsc_pages"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "date",
            "normalized_url",
            "country",
            "device",
            name="uq_facts_gsc_pages_grain",
        ),
        Index("ix_facts_gsc_pages_client_date", "client_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    device: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    impressions: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    clicks: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    ctr: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    average_position: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FactGscQueryPage(Base):
    __tablename__ = "facts_gsc_query_pages"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "date",
            "query",
            "normalized_url",
            "country",
            "device",
            name="uq_facts_gsc_query_pages_grain",
        ),
        CheckConstraint("length(trim(query)) > 0", name="ck_facts_gsc_query_pages_query_nonblank"),
        Index("ix_facts_gsc_query_pages_client_date", "client_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    raw_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    device: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    impressions: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    clicks: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    ctr: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    average_position: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
