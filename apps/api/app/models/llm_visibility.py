"""LLM visibility: runs that ask AI platforms the watchlist's paired prompts, and what each answered.

Ported from the standalone llmviz tool. A run is a thing that happened on a date; its responses are
kept whole so a report can quote what the platform actually said.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ClientLlmSettings(Base):
    """How to spot a client and its competitors in an answer. Derived from the name and domains until edited."""

    __tablename__ = "client_llm_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, unique=True
    )
    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_patterns: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, default=list)
    #: `{competitor domain: {"name": ..., "patterns": [...]}}`; a competitor not listed here is derived from its domain.
    competitors: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LlmRun(Base):
    __tablename__ = "llm_runs"
    __table_args__ = (Index("ix_llm_runs_client_started", "client_id", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: running | completed | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    platforms: Mapped[list] = mapped_column(ARRAY(String(16)), nullable=False, default=list)
    total_calls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class LlmResponse(Base):
    __tablename__ = "llm_responses"
    __table_args__ = (
        Index("ix_llm_responses_run", "run_id"),
        Index("ix_llm_responses_client_created", "client_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("llm_runs.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    #: The watchlist bucket the prompt's keyword belongs to.
    topic_cluster: Mapped[str | None] = mapped_column(String(160), nullable=True)
    keyword: Mapped[str | None] = mapped_column(String(400), nullable=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Cited + Mentioned | Cited | Mentioned | Not visible | Error
    visibility_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    brand_mentioned: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    url_cited: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cited_urls: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)
    position: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sources_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    competitors_mentioned: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)
    all_brands_ordered: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)
    other_brands_mentioned: Mapped[list | None] = mapped_column(ARRAY(Text), nullable=True)
    brand_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_brands: Mapped[int | None] = mapped_column(Integer, nullable=True)
    full_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClientLlmPrompt(Base):
    """A prompt asked on every run that is not a watchlist keyword's paired prompt: brand checks and niche questions."""

    __tablename__ = "client_llm_prompts"
    __table_args__ = (UniqueConstraint("client_id", "prompt_key", name="uq_client_llm_prompt"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    #: Lower-cased and whitespace-collapsed, so the same question is never asked twice.
    prompt_key: Mapped[str] = mapped_column(String(600), nullable=False)
    #: The group its answers count under in share of voice, e.g. "Brand check".
    topic_cluster: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
