import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StagingSerKeyword(Base):
    __tablename__ = "staging_ser_keywords"
    __table_args__ = (Index("ix_staging_ser_keywords_job", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    site_engine_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    keyword_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StagingSerPosition(Base):
    __tablename__ = "staging_ser_positions"
    __table_args__ = (Index("ix_staging_ser_positions_job", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    site_engine_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    keyword_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    position_change: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    ranking_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StagingSerCompetitor(Base):
    __tablename__ = "staging_ser_competitors"
    __table_args__ = (Index("ix_staging_ser_competitors_job", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    site_engine_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    competitor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    metric_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StagingSerSiteSummary(Base):
    __tablename__ = "staging_ser_site_summary"
    __table_args__ = (Index("ix_staging_ser_site_summary_job", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    metric_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    visibility: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    visibility_percent: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    top5: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top10: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top30: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FactSerSiteSummary(Base):
    __tablename__ = "facts_ser_site_summary"
    __table_args__ = (
        UniqueConstraint("client_id", "metric_date", name="uq_facts_ser_site_summary_grain"),
        Index("ix_facts_ser_site_summary_client_date", "client_id", "metric_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    visibility: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    visibility_percent: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    top5: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top10: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top30: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FactSerKeyword(Base):
    __tablename__ = "facts_ser_keywords"
    __table_args__ = (
        UniqueConstraint("client_id", "site_engine_id", "keyword_id", name="uq_facts_ser_keywords_grain"),
        Index("ix_facts_ser_keywords_client", "client_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    site_engine_id: Mapped[str] = mapped_column(String(64), nullable=False)
    keyword_id: Mapped[str] = mapped_column(String(64), nullable=False)
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    current_position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    previous_position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    ranking_change: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    visibility: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    earned_serp_features: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    ranking_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FactSerRanking(Base):
    __tablename__ = "facts_ser_rankings"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "date",
            "site_engine_id",
            "keyword_id",
            name="uq_facts_ser_rankings_grain",
        ),
        Index("ix_facts_ser_rankings_client_date", "client_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    site_engine_id: Mapped[str] = mapped_column(String(64), nullable=False)
    keyword_id: Mapped[str] = mapped_column(String(64), nullable=False)
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    position_change: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    volume: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    ranking_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FactSerCompetitor(Base):
    __tablename__ = "facts_ser_competitors"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "site_engine_id",
            "competitor_id",
            name="uq_facts_ser_competitors_grain",
        ),
        Index("ix_facts_ser_competitors_client", "client_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    site_engine_id: Mapped[str] = mapped_column(String(64), nullable=False)
    competitor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    metric_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StagingSerAiPrompt(Base):
    __tablename__ = "staging_ser_ai_prompts"
    __table_args__ = (Index("ix_staging_ser_ai_prompts_job", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    llm_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_llm_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    search_volume: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    search_intent: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StagingSerAiCheck(Base):
    __tablename__ = "staging_ser_ai_checks"
    __table_args__ = (Index("ix_staging_ser_ai_checks_job", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    llm_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    mention_position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    urls_count: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    mentions_count: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    organic_overlap_percent: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StagingSerAiPresence(Base):
    __tablename__ = "staging_ser_ai_presence"
    __table_args__ = (Index("ix_staging_ser_ai_presence_job", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    metric_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_market: Mapped[str | None] = mapped_column(String(8), nullable=True)
    target_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_presence_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    link_presence_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_presence_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StagingSerAiTrackerStats(Base):
    __tablename__ = "staging_ser_ai_tracker_stats"
    __table_args__ = (Index("ix_staging_ser_ai_tracker_stats_job", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sync_jobs.id"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False)
    metric_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    prompts_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mention_presence_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    link_presence_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    mention_top3_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    link_top3_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FactSerAiPrompt(Base):
    __tablename__ = "facts_ser_ai_prompts"
    __table_args__ = (
        UniqueConstraint("client_id", "llm_id", "prompt_id", name="uq_facts_ser_ai_prompts_grain"),
        Index("ix_facts_ser_ai_prompts_client", "client_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    llm_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_llm_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engine: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    search_volume: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    search_intent: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    url_position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    mention_position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    url_position_change: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    mention_position_change: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    brand_mentioned: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    brand_cited: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    citation_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_visibility: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    ai_sov: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    checked_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FactSerAiCheck(Base):
    __tablename__ = "facts_ser_ai_checks"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "date",
            "llm_id",
            "prompt_id",
            name="uq_facts_ser_ai_checks_grain",
        ),
        Index("ix_facts_ser_ai_checks_client_date", "client_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    llm_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    url_position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    mention_position: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    urls_count: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    mentions_count: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    organic_overlap_percent: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    brand_mentioned: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    brand_cited: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FactSerAiTrackerStats(Base):
    __tablename__ = "facts_ser_ai_tracker_stats"
    __table_args__ = (
        UniqueConstraint("client_id", "metric_date", name="uq_facts_ser_ai_tracker_stats_grain"),
        Index("ix_facts_ser_ai_tracker_stats_client_date", "client_id", "metric_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    prompts_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mention_presence_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    link_presence_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    mention_top3_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    link_top3_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FactSerAiPresence(Base):
    __tablename__ = "facts_ser_ai_presence"
    __table_args__ = (
        UniqueConstraint("client_id", "metric_date", name="uq_facts_ser_ai_presence_grain"),
        Index("ix_facts_ser_ai_presence_client_date", "client_id", "metric_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_market: Mapped[str | None] = mapped_column(String(8), nullable=True)
    target_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_presence_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    link_presence_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_presence_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
