import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
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


class KeywordTarget(Base):
    """Which page is meant to own a term.

    The playbook's first source for "which page should rank for this", and
    the one thing no amount of data could supply: Search Console reports
    where Google currently shows a page, which on a term the client does
    not rank for is either nothing or the wrong page. Matching titles was
    tried and chose a neighbouring service page.

    So a person says it once, and every finding about that term stops
    guessing.
    """

    __tablename__ = "keyword_targets"
    __table_args__ = (
        UniqueConstraint("client_id", "keyword", name="uq_keyword_targets_grain"),
        Index("ix_keyword_targets_client", "client_id"),
        Index("ix_keyword_targets_priority", "client_id", "priority"),
        CheckConstraint(
            "term_role IS NULL OR term_role IN ('primary', 'secondary')",
            name="ck_keyword_targets_term_role",
        ),
        CheckConstraint(
            "source IN ('confirmed', 'suggested')",
            name="ck_keyword_targets_source",
        ),
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
    target_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: primary | secondary | None. A primary term earns a title rewrite; a
    #: secondary one earns a section. Null means nobody has said, which is
    #: not the same as secondary, so the rules that care must check.
    term_role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: The SE Ranking group this term belongs to, copied at confirmation
    #: time. The fact table has it too, but a term can be mapped before it
    #: is tracked, and a group can be renamed under us.
    group_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Whether this is one of the terms the client is actually judged on.
    #: V1 reads "priority-group keywords" and nothing marked a group before.
    priority: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: confirmed | suggested. The engine reads confirmed rows only — a
    #: proposal from the embedding matcher is a proposal until somebody
    #: agrees with it.
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="confirmed")
    #: How sure the suggester was, for ordering a review queue. Never read
    #: by a rule.
    confidence: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MonthlyRecord(Base):
    """One saved run per client per month.

    The engine used to recompute on every page view, which made the page a
    different thing each time it loaded: a run that named Visibility in the
    morning could name Leads in the afternoon because a sync landed, with
    nothing recording that it changed or what it said before.

    Almost everything downstream needs a run to be a thing that happened.
    `held_since` and the two-month hold need last month's answer; "do not
    prescribe this action on this URL again before its check date" needs the
    date it was prescribed; the results loop needs what was promised 28 to 45
    days ago. None of that works against a function.
    """

    __tablename__ = "monthly_records"
    __table_args__ = (
        UniqueConstraint("client_id", "month", name="uq_monthly_records_grain"),
        Index("ix_monthly_records_client_month", "client_id", "month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    #: "2026-10". One plan a month; re-running replaces it.
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    run_saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: The newest day the data actually covered, not the day asked for.
    data_through: Mapped[date | None] = mapped_column(Date, nullable=True)
    constraint_name: Mapped[str] = mapped_column(String(32), nullable=False)
    held_since: Mapped[str] = mapped_column(String(7), nullable=False)
    confidence: Mapped[str] = mapped_column(String(8), nullable=False)
    #: The whole record, to monthly-record.schema.json. Stored as one document
    #: rather than fifteen tables that have to be joined back into exactly the
    #: shape the page reads — every join a chance for the page to disagree
    #: with the run.
    record: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EngineAction(Base):
    """Workflow state for one action or incident, written by the page.

    Kept apart from the record on purpose. The record is what the engine
    decided and must not change when somebody assigns a task; this is what
    the team did about it. `uid` is stable across re-runs of the same month,
    so an assignment made on Monday survives a re-run on Tuesday.
    """

    __tablename__ = "engine_actions"
    __table_args__ = (
        UniqueConstraint("client_id", "uid", name="uq_engine_actions_uid"),
        Index("ix_engine_actions_client_month", "client_id", "month"),
        CheckConstraint(
            "status IN ('planned', 'assigned', 'done', 'skipped')",
            name="ck_engine_actions_status",
        ),
        CheckConstraint(
            "result IS NULL OR result IN ('improved', 'no_change', 'worse', 'waiting')",
            name="ck_engine_actions_result",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uid: Mapped[str] = mapped_column(String(128), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="action")
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    due: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: What was on screen when somebody acted on this slot. `uid` is keyed on
    #: the slot number, so a re-run that reshuffles the slots would otherwise
    #: carry an assignment onto a different action without saying so.
    action_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Set when the action was pushed to Teamwork, so a second press links
    #: rather than creating a duplicate task.
    teamwork_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    teamwork_task_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipped_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: The results loop, filled on the check date rather than at prescription.
    before_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    after_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExcludedPage(Base):
    """A page this client's engine should not look at.

    Boys Electrical's traffic branch failed on a careers page — 52 sessions,
    no conversions — which is correct and useless, because nobody is being
    paid to recruit electricians this quarter.

    Per client, not a global pattern list: some agencies really are running
    recruitment campaigns, and deciding that centrally decides it for
    everyone. A pattern ending in `*` takes the section.
    """

    __tablename__ = "excluded_pages"
    __table_args__ = (
        UniqueConstraint("client_id", "url_pattern", name="uq_excluded_pages_grain"),
        Index("ix_excluded_pages_client", "client_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    url_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    #: In the words of whoever excluded it, so a decision taken in March is
    #: legible in September.
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ConstraintOverride(Base):
    """A month where somebody overruled the engine's answer.

    Not "this page is irrelevant" — that is an exclusion — but "I know what
    the numbers say, work on visibility anyway". One per client per month,
    because overriding is a decision about this month's plan rather than a
    standing instruction that quietly never expires.
    """

    __tablename__ = "constraint_overrides"
    __table_args__ = (
        UniqueConstraint("client_id", "month", name="uq_constraint_overrides_grain"),
        CheckConstraint(
            "constraint_name IN ('visibility', 'traffic', 'leads', "
            "'visibility_expansion')",
            name="ck_constraint_overrides_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    constraint_name: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
