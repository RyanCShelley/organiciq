"""A task an operator confirmed from the Decision engine.

Confirming is the human step. A rule's prescription and an unconfirmed suggestion both
become a task the same way, so a suggestion is never acted on until a person has said yes.
`kind` keeps which it was, and the Teamwork description says so.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

STATUSES = ("confirmed", "sent", "shipped", "dropped")


class EngineTask(Base):
    __tablename__ = "engine_tasks"
    __table_args__ = (
        UniqueConstraint("client_id", "month", "rule_id", "search", "page_url", name="uq_engine_task_once"),
        Index("ix_engine_tasks_client_month", "client_id", "month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    #: The month the work is planned for, YYYY-MM.
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    #: prescription (a rule fired) | suggestion (unconfirmed until a person confirmed it)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(16), nullable=False)
    search: Mapped[str] = mapped_column(Text, nullable=False)
    page_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    why: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    done_when: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric: Mapped[str | None] = mapped_column(Text, nullable=True)
    effort_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="confirmed")
    confirmed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    assignee_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due: Mapped[date | None] = mapped_column(Date, nullable=True)
    teamwork_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    teamwork_task_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Subtask key -> Teamwork id, for the subtasks made under the task.
    teamwork_subtasks: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: What the page and topic looked like in the 28 days before it shipped.
    baseline: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    #: The day the 28 days after shipping are complete in Search Console, and so the day it can be judged.
    check_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: What the same numbers were over the 28 days after, kept once measured so it never moves again.
    outcome: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
