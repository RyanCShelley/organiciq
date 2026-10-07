import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ConversionDefinition(Base):
    __tablename__ = "conversion_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    conversion_name: Mapped[str] = mapped_column(String(255), nullable=False)
    conversion_type: Mapped[str] = mapped_column(String(100), nullable=False, default="lead")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrganicChannel(str, enum.Enum):
    ORGANIC_SEARCH = "organic_search"
    AI_REFERRAL = "ai_referral"
    DIRECT_UNATTRIBUTED = "direct_unattributed"
    PAID_SEARCH = "paid_search"
    REFERRAL = "referral"
    SOCIAL = "social"
    EMAIL = "email"
    OTHER = "other"


class ChannelRule(Base):
    __tablename__ = "channel_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_medium: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_host_contains: Mapped[str | None] = mapped_column(String(255), nullable=True)
    channel: Mapped[OrganicChannel] = mapped_column(
        Enum(OrganicChannel, name="organic_channel", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TopicStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    topic_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[TopicStatus] = mapped_column(
        Enum(TopicStatus, name="topic_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TopicStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ClientConversionPage(Base):
    """The pages this client counts as a conversion.

    `classify_page_url` guesses from URL fragments — /contact, /demo,
    /quote — which is right often enough to have hidden how often it is
    wrong. A client whose offer lives at /get-a-leak-check, or whose
    /contact page is a staff directory, was classified by a list written
    for somebody else.

    Declared pages win. With none declared the old fragments still apply,
    so nothing changes for a client until someone says otherwise.
    """

    __tablename__ = "client_conversion_pages"
    __table_args__ = (
        UniqueConstraint("client_id", "normalized_url", name="uq_client_conversion_page"),
        Index("ix_client_conversion_pages_client", "client_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Which part of the journey this offer serves, so a page can be sent to
    #: the offer that matches where its reader is rather than to the one
    #: that happens to be primary.
    stage: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RefreshQueueEntry(Base):
    """Pages already booked for a content refresh this month.

    A finding on a page that is about to be rewritten anyway is not a
    growth action; the work is already paid for. Nothing populates this
    yet — it is a stub, and an empty table means the gate never fires.
    """

    __tablename__ = "refresh_queue"
    __table_args__ = (
        UniqueConstraint("client_id", "normalized_url", "month", name="uq_refresh_queue_grain"),
        Index("ix_refresh_queue_client_month", "client_id", "month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    #: First of the month the refresh is booked for.
    month: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
