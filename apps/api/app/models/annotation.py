"""Annotations — causal history of meaningful client changes."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.decision import GrowthAction


class AnnotationType(str, enum.Enum):
    GROWTH_ACTION = "growth_action"
    CONTENT_PUBLISHED = "content_published"
    CONTENT_UPDATED = "content_updated"
    TECHNICAL_CHANGE = "technical_change"
    WEBSITE_CHANGE = "website_change"
    CONVERSION_CHANGE = "conversion_change"
    CAMPAIGN_CHANGE = "campaign_change"
    ALGORITHM_EVENT = "algorithm_event"
    MANUAL_NOTE = "manual_note"


class AnnotationResult(str, enum.Enum):
    IMPROVED = "improved"
    NO_MEANINGFUL_CHANGE = "no_meaningful_change"
    DECLINED = "declined"
    NOT_ENOUGH_DATA = "not_enough_data"
    NOT_YET_MEASURED = "not_yet_measured"


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("decisions.id"), nullable=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    annotation_type: Mapped[AnnotationType] = mapped_column(
        Enum(AnnotationType, name="annotation_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    growth_action: Mapped[GrowthAction | None] = mapped_column(
        Enum(
            GrowthAction,
            name="growth_action",
            values_callable=lambda x: [e.value for e in x],
            create_constraint=False,
            native_enum=True,
        ),
        nullable=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.id"), nullable=True)
    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    baseline_metrics_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    success_metric: Mapped[str | None] = mapped_column(String(255), nullable=True)
    teamwork_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    completed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    measurement_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    measurement_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    post_action_metrics_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[AnnotationResult] = mapped_column(
        Enum(AnnotationResult, name="annotation_result", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=AnnotationResult.NOT_YET_MEASURED,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact_summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
