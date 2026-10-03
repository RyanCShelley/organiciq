import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DecisionType(str, enum.Enum):
    BOTTLENECK = "bottleneck"
    OPPORTUNITY = "opportunity"
    EVIDENCE = "evidence"
    CONTENT_PLANNING_SIGNAL = "content_planning_signal"


class GrowthAction(str, enum.Enum):
    INTERNAL_LINKING = "internal_linking"
    TECHNICAL_SEO = "technical_seo"
    SERP_CTR = "serp_ctr"
    # Stored value kept for DB enum compatibility; product name is Search & AI Visibility.
    AI_VISIBILITY = "structured_data_ai"
    CONVERSION_PATH = "conversion_path"


class DecisionPriority(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DismissalReason(str, enum.Enum):
    """Why a recommendation was turned down.

    Free text meant the 3x override rule counted disagreements it could not
    read: "wrong data" is a bug report and "already done" is a scheduling
    note, and neither says the rule is a bad fit. Stored as text so no
    database enum has to be altered to add one, validated on the way in.
    """

    WRONG_DATA = "wrong_data"
    ALREADY_DONE = "already_done"
    NOT_RELEVANT = "not_relevant"
    CLIENT_DECLINED = "client_declined"
    OTHER = "other"


class DecisionStatus(str, enum.Enum):
    NEW = "new"
    REVIEWED = "reviewed"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    TASK_CREATED = "task_created"
    COMPLETED = "completed"
    MEASURING = "measuring"
    VALIDATED = "validated"


class DiagnosticLayer(str, enum.Enum):
    VISIBILITY = "visibility"
    TRAFFIC = "traffic"
    CONVERSION = "conversion"


class DecisionThreshold(Base):
    __tablename__ = "decision_thresholds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, unique=True
    )
    thresholds: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        UniqueConstraint("client_id", "rule_key", "date_range_start", "date_range_end", name="uq_decisions_rule_window"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    rule_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decision_type: Mapped[DecisionType] = mapped_column(
        Enum(DecisionType, name="decision_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    growth_action: Mapped[GrowthAction | None] = mapped_column(
        Enum(GrowthAction, name="growth_action", values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    diagnostic_layer: Mapped[DiagnosticLayer] = mapped_column(
        Enum(DiagnosticLayer, name="diagnostic_layer", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    priority: Mapped[DecisionPriority] = mapped_column(
        Enum(DecisionPriority, name="decision_priority", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DecisionPriority.MEDIUM,
    )
    status: Mapped[DecisionStatus] = mapped_column(
        Enum(DecisionStatus, name="decision_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DecisionStatus.NEW,
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=True)
    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    baseline_metrics_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    success_metric: Mapped[str] = mapped_column(String(255), nullable=False)
    date_range_start: Mapped[date] = mapped_column(Date, nullable=False)
    date_range_end: Mapped[date] = mapped_column(Date, nullable=False)
    dismissal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_score: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    impact: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    urgency: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    effort: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)


class KeywordPageMap(Base):
    """Which page is meant to own a term.

    The playbook's first source for "which page should rank for this", and
    the one thing no amount of data could supply: Search Console reports
    where Google currently shows a page, which on a term the client does
    not rank for is either nothing or the wrong page. Matching titles was
    tried and chose a neighbouring service page.

    So a person says it once, and every finding about that term stops
    guessing.
    """

    __tablename__ = "keyword_page_map"
    __table_args__ = (
        UniqueConstraint("client_id", "keyword", name="uq_keyword_page_map_grain"),
        Index("ix_keyword_page_map_client", "client_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    #: Stored lowercase: a watchlist entry and a Search Console query differ
    #: in case far more often than in substance.
    keyword: Mapped[str] = mapped_column(String(512), nullable=False)
    #: Null means "deliberately no page yet" — a decision, and different
    #: from never having been asked.
    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
