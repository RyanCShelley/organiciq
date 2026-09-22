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
    #: Inbound links that are neither navigation nor site-wide — whether anyone
    #: actually references this page, as opposed to it sitting in a menu.
    inbound_editorial_links: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    robots: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_by_robots: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    redirect_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    redirect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


#: Crawl sources that may write page snapshots. Both run during the parallel
#: period so their output can be diffed before anything is switched over.
CRAWL_SOURCE_SE_RANKING = "se_ranking_audit"
CRAWL_SOURCE_FIRST_PARTY = "site_crawl"


class FactCrawlPageSnapshot(Base):
    """Latest crawl snapshot per page, per crawl source."""

    __tablename__ = "facts_crawl_page_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "source", "normalized_url", name="uq_facts_crawl_page_snapshots_grain"
        ),
        Index("ix_facts_crawl_page_snapshots_client", "client_id"),
        Index("ix_facts_crawl_page_snapshots_client_source", "client_id", "source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default=CRAWL_SOURCE_SE_RANKING
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    indexable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    inbound_internal_links: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_sitemap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Inbound links that are neither navigation nor site-wide — whether anyone
    #: actually references this page, as opposed to it sitting in a menu.
    inbound_editorial_links: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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
    """Crawl issue codes (page-level or site-level), per crawl source."""

    __tablename__ = "facts_crawl_page_issues"
    __table_args__ = (
        Index("ix_facts_crawl_page_issues_client", "client_id"),
        Index("ix_facts_crawl_page_issues_client_code", "client_id", "issue_code"),
        Index("ix_facts_crawl_page_issues_client_source", "client_id", "source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default=CRAWL_SOURCE_SE_RANKING
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    issue_code: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FactCrawlPageSchema(Base):
    """
    Structured data found on a page, one row per block.

    The raw block is kept because the checks we run against schema will change
    as we learn what to look for, and re-crawling every client to answer a new
    question is exactly what owning the crawler is meant to avoid.

    A block that failed to parse is still recorded, with the reason: schema that
    is present but invalid is indistinguishable from absent to any consumer, and
    is invisible in every report we have today.
    """

    __tablename__ = "facts_crawl_page_schema"
    __table_args__ = (
        Index("ix_facts_crawl_page_schema_client", "client_id"),
        Index("ix_facts_crawl_page_schema_client_url", "client_id", "normalized_url"),
        Index("ix_facts_crawl_page_schema_client_type", "client_id", "schema_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    #: json_ld | microdata | rdfa
    syntax: Mapped[str] = mapped_column(String(16), nullable=False)
    #: schema.org @type, bare (e.g. "LocalBusiness"); null when unparseable.
    schema_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    #: The source text, kept only when parsing failed so it can be diagnosed.
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FactCrawlInternalLink(Base):
    """
    One edge of a client's internal link graph.

    The crawler always built this and then reduced it to a per-page count before
    storing anything. A count cannot answer a question about clusters — "which
    of these posts fail to link to their pillar" needs the edges, and the anchor
    text that goes with them.
    """

    __tablename__ = "facts_crawl_internal_links"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "source", "from_url", "to_url", name="uq_facts_crawl_internal_links_grain"
        ),
        Index("ix_facts_crawl_internal_links_client_to", "client_id", "to_url"),
        Index("ix_facts_crawl_internal_links_client_from", "client_id", "from_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default=CRAWL_SOURCE_FIRST_PARTY)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    from_url: Mapped[str] = mapped_column(Text, nullable=False)
    to_url: Mapped[str] = mapped_column(Text, nullable=False)
    anchor_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Outside nav/header/footer/menu/aside on the linking page.
    in_content: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Site furniture rather than an editorial reference.
    is_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
