"""Concepts a person has approved as Wikidata entities for a client, and the audits and markup generated for its pages."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ClientSchemaConcept(Base):
    """A concept (the brand, a product line, a topic) tied to its Wikidata item. Only these may be linked from generated markup."""

    __tablename__ = "client_schema_concepts"
    __table_args__ = (UniqueConstraint("client_id", "name_key", name="uq_client_schema_concept_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_key: Mapped[str] = mapped_column(String(255), nullable=False)
    qid: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SchemaPageReport(Base):
    """The latest model-written audit or corrected markup for one page, kept with what it cost."""

    __tablename__ = "schema_page_reports"
    __table_args__ = (Index("ix_schema_page_reports_client_url", "client_id", "url", "kind"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    #: audit or markup.
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    depth: Mapped[str] = mapped_column(String(16), nullable=False)
    #: running, done or failed.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClientSchemaIgnore(Base):
    """Something a person said does not apply to this client, so the Schema screen stops counting it.

    scope `check`: an entity check ("wikidata"); `expect`: a markup type not expected of a kind of page ("homepage:WebSite");
    `page_type`: a whole kind of page ("homepage"); `page`: one address; `cleanup`: one recurring cleanup (its text, addresses removed).
    """

    __tablename__ = "client_schema_ignores"
    __table_args__ = (UniqueConstraint("client_id", "scope", "key", name="uq_client_schema_ignore"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CtrTitleDraft(Base):
    """Title tags a model wrote for one page, from the page's own search data. A draft for a person to check; nothing is sent anywhere."""

    __tablename__ = "ctr_title_drafts"
    __table_args__ = (Index("ix_ctr_title_drafts_client_url", "client_id", "url"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[str] = mapped_column(String(16), nullable=False)
    #: running, done or failed.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The range of dates the searches were read from.
    range_from: Mapped[str] = mapped_column(String(10), nullable=False)
    range_to: Mapped[str] = mapped_column(String(10), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InlinkState(Base):
    """What a person did with a suggested link, so it is not suggested again: ignored (this pair, or this target page) or confirmed live."""

    __tablename__ = "inlink_states"
    __table_args__ = (UniqueConstraint("client_id", "source_url", "target_url", name="uq_inlink_state"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    #: Empty for a whole target page ("do not suggest links to this page").
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    #: ignored or live.
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    anchor: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
