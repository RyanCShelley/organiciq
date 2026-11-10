"""The consulting portal's records: what we know about the client's business, then (in later steps) recommendations, reports and their history."""

from __future__ import annotations

import uuid
from datetime import datetime

from datetime import date

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ConsultingProfile(Base):
    """The Understand step: goals, audiences, constraints and the brand's editorial rules, written by the consultant. Internal: the client does not see the notes."""

    __tablename__ = "consulting_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, unique=True)
    goals: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    audiences: Mapped[str | None] = mapped_column(Text, nullable=True)
    markets: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_services: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints: Mapped[str | None] = mapped_column(Text, nullable=True)
    editorial_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    resources: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Many consulting clients are hired for AI visibility: when set, GEO findings are surfaced first in drafts.
    ai_visibility_focus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


REVIEW_STATES = ("draft", "under_review", "approved", "published", "archived")
IMPL_STATUSES = ("recommended", "planned", "in_progress", "completed", "blocked")


class ConsultingRecommendation(Base):
    """One brief for a client's own team: what we found, why it matters, exactly what to do and how success is measured.

    Advisory only: publishing shows it in the client's portal and creates no work for SMA. Two tracks run side by side. `review_state` is the consultant's
    (draft, under review, approved, published, archived). `impl_status` is what happened on the client's side, and is often unknown: it says who reported it
    (the consultant recording what the client said, the client, or the live check), and verification and measurement are filled only when there is evidence.
    """

    __tablename__ = "consulting_recommendations"
    __table_args__ = (Index("ix_consulting_recs_client_state", "client_id", "review_state"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    #: visibility | traffic | leads, the engine's own branches.
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    #: seo | geo | both: whether it helps search, AI visibility, or both (dual optimization).
    focus: Mapped[str] = mapped_column(String(8), nullable=False, default="seo", server_default="seo")
    #: Where the draft came from: decision_engine, site_health, geo, ctr, inlinks, schema, content_gap, content_refresh, optimizer or manual.
    source_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="manual", server_default="manual")
    source_ref: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    finding: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: hypothesis | confirmed (two independent signals).
    cause_kind: Mapped[str] = mapped_column(String(12), nullable=False, default="hypothesis", server_default="hypothesis")
    cause_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: `[{"text": "..."}]`, the checklist the client's team follows.
    instructions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    #: `[{"url": "...", "check": {"state": "unchecked|exists|canonical|redirect|new|offsite", "live_url": ..., "note": ..., "checked_at": ...}}]`.
    target_urls: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="medium", server_default="medium")
    expected_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String(8), nullable=False, default="medium", server_default="medium")
    confidence_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    effort_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: `[{"metric", "value", "source", "period"}]` and `[{"metric", "baseline", "target", "window_days"}]`.
    baseline: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    success_metrics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    measure_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: `[{"text", "source", "as_of"}]`.
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    #: Only SMA sees this.
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_state: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    impl_status: Mapped[str] = mapped_column(String(12), nullable=False, default="recommended", server_default="recommended")
    #: consultant | client | live_check: who said so.
    impl_status_source: Mapped[str | None] = mapped_column(String(12), nullable=True)
    impl_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    implemented_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    implemented_on_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    client_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_links: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    last_follow_up_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: unverified | verified | not_seen | unreadable.
    verification: Mapped[str] = mapped_column(String(12), nullable=False, default="unverified", server_default="unverified")
    verified_how: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConsultingRecommendationEvent(Base):
    """Every change to a brief: who, when, what. Answers "what did we recommend, what was said, what moved"."""

    __tablename__ = "consulting_recommendation_events"
    __table_args__ = (Index("ix_consulting_rec_events_rec", "recommendation_id", "at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("consulting_recommendations.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    #: created | edited | state | progress | verified | note.
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    from_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    by: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConsultingReport(Base):
    """One month's report to a client: the consultant's own analysis, with the headline numbers frozen at the moment it is published.

    The numbers are frozen so the client is shown what the consultant saw and wrote about, not figures that move underneath the words. A draft shows the
    live numbers to the consultant; publishing keeps them.
    """

    __tablename__ = "consulting_reports"
    __table_args__ = (UniqueConstraint("client_id", "kind", "period_month", name="uq_consulting_report_kind_month"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    period_month: Mapped[str] = mapped_column(String(7), nullable=False)
    #: monthly (the performance report) | executive (the leadership summary).
    kind: Mapped[str] = mapped_column(String(12), nullable=False, default="monthly", server_default="monthly")
    #: `{"topics": "...", "rankings": "..."}`: a short note from the consultant under a section, for context the numbers cannot give.
    notes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: `{"going_well": [...], "to_watch": [...], "gaps": [...]}`: short points, one per line as the consultant writes them.
    highlights: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    #: draft | published.
    review_state: Mapped[str] = mapped_column(String(12), nullable=False, default="draft", server_default="draft")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    metrics_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
