import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StagingSerAuditPage(Base):
    __tablename__ = "staging_ser_audit_pages"
    __table_args__ = (Index("ix_staging_ser_audit_pages_job", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    audit_id: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    indexable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    inbound_internal_links: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_sitemap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    robots: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_by_robots: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    redirect_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    redirect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FactCrawlPageSnapshot(Base):
    """Latest crawl/audit snapshot per page (SE Ranking Website Audit or equivalent)."""

    __tablename__ = "facts_crawl_page_snapshots"
    __table_args__ = (
        UniqueConstraint("client_id", "normalized_url", name="uq_facts_crawl_page_snapshots_grain"),
        Index("ix_facts_crawl_page_snapshots_client", "client_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    indexable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    inbound_internal_links: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_sitemap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    robots: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_by_robots: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    redirect_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    redirect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StagingSerAuditIssue(Base):
    __tablename__ = "staging_ser_audit_issues"
    __table_args__ = (Index("ix_staging_ser_audit_issues_job", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    audit_id: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    issue_code: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FactCrawlPageIssue(Base):
    """SE Ranking Website Audit issue codes (page-level or site-level)."""

    __tablename__ = "facts_crawl_page_issues"
    __table_args__ = (
        Index("ix_facts_crawl_page_issues_client", "client_id"),
        Index("ix_facts_crawl_page_issues_client_code", "client_id", "issue_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    issue_code: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
