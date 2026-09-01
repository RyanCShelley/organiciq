import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
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
