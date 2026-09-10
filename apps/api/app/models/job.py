import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import Index

from app.core.db import Base


class SyncJobStatus(str, enum.Enum):
    QUEUED = "queued"
    FETCHING = "fetching"
    STAGING = "staging"
    NORMALIZING = "normalizing"
    VALIDATING = "validating"
    SUCCESSFUL = "successful"
    PARTIAL = "partial"
    FAILED = "failed"


class ValidationStatus(str, enum.Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SyncJob(Base):
    __tablename__ = "sync_jobs"
    __table_args__ = (
        Index(
            "uq_sync_jobs_active_client_source",
            "client_id",
            "source",
            unique=True,
            postgresql_where=text(
                "status IN ('queued', 'fetching', 'staging', 'normalizing', 'validating')"
            ),
        ),
        # Worker claim path, run every poll cycle.
        Index("ix_sync_jobs_status_created", "status", "created_at"),
        Index("ix_sync_jobs_client_created", "client_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[SyncJobStatus] = mapped_column(
        Enum(SyncJobStatus, name="sync_job_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SyncJobStatus.QUEUED,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_fetched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_written: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fact_watermark: Mapped[date | None] = mapped_column(Date, nullable=True)
    validation_status: Mapped[ValidationStatus | None] = mapped_column(
        Enum(
            ValidationStatus,
            name="validation_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DataWatermark(Base):
    __tablename__ = "data_watermarks"
    __table_args__ = (
        Index("uq_data_watermarks_client_source", "client_id", "source", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_through_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_status: Mapped[ValidationStatus | None] = mapped_column(
        Enum(
            ValidationStatus,
            name="validation_status",
            values_callable=lambda x: [e.value for e in x],
            create_type=False,
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
