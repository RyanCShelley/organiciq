"""Google Ads performance for clients on Ads Accelerator, kept by day.

Rows are written by the Google Ads pull (not built yet) or, for a demo, by a seed. `source` says which.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AdsDaily(Base):
    """One day of one campaign and ad group, split by device.

    `eligible_impressions` is the searches the ads could have shown on (impressions divided by the search impression share).
    """

    __tablename__ = "ads_daily"
    __table_args__ = (
        UniqueConstraint("client_id", "account_id", "date", "campaign", "ad_group", "market", "device", "network", name="uq_ads_daily_account_grain"),
        Index("ix_ads_daily_client_date", "client_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    #: Which Google Ads account the row came from (a client can have several, for example search ads and Local Services Ads).
    account_id: Mapped[str] = mapped_column(String(20), nullable=False, default="", server_default="")
    campaign: Mapped[str] = mapped_column(Text, nullable=False)
    ad_group: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    #: Not used: a pulled day is split by device only, and markets are in `ads_market_daily`. Kept because migrations only add.
    market: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    device: Mapped[str] = mapped_column(String(16), nullable=False, default="", server_default="")
    network: Mapped[str] = mapped_column(String(24), nullable=False, default="search", server_default="search")
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    conversions: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    eligible_impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="google_ads", server_default="google_ads")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdsMarketDaily(Base):
    """One day of one campaign in one market (a country). Google reports markets apart from ad groups and devices, so they are kept apart."""

    __tablename__ = "ads_market_daily"
    __table_args__ = (
        UniqueConstraint("client_id", "account_id", "date", "campaign", "market", name="uq_ads_market_daily_account_grain"),
        Index("ix_ads_market_daily_client_date", "client_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    account_id: Mapped[str] = mapped_column(String(20), nullable=False, default="", server_default="")
    campaign: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(Text, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    conversions: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="google_ads", server_default="google_ads")


class AdsSearchTerm(Base):
    """What people searched for, by day, for the clicks Google lists (searches made by only a few people are not listed)."""

    __tablename__ = "ads_search_terms"
    __table_args__ = (
        UniqueConstraint("client_id", "account_id", "date", "term", "ad_group", name="uq_ads_search_terms_account_grain"),
        Index("ix_ads_search_terms_client_date", "client_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    account_id: Mapped[str] = mapped_column(String(20), nullable=False, default="", server_default="")
    term: Mapped[str] = mapped_column(Text, nullable=False)
    ad_group: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    conversions: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="google_ads", server_default="google_ads")


class ClientAdsAccount(Base):
    """A Google Ads account a client is: search ads, Local Services Ads, and so on. A client can have several."""

    __tablename__ = "client_ads_accounts"
    __table_args__ = (UniqueConstraint("client_id", "customer_id", name="uq_client_ads_account"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    #: Digits only.
    customer_id: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    #: "ads" (search and other campaigns) or "lsa" (Local Services Ads).
    kind: Mapped[str] = mapped_column(String(8), nullable=False, default="ads", server_default="ads")
    last_pull_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdsLsaLead(Base):
    """One Local Services Ads lead, by the day it was created. Its status changes later (new, active, booked, declined), so recent ones are pulled again."""

    __tablename__ = "ads_lsa_leads"
    __table_args__ = (
        UniqueConstraint("client_id", "account_id", "lead_id", name="uq_ads_lsa_leads_lead"),
        Index("ix_ads_lsa_leads_client_date", "client_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[str] = mapped_column(String(20), nullable=False, default="", server_default="")
    lead_id: Mapped[str] = mapped_column(String(40), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    #: PHONE_CALL, MESSAGE or BOOKING, as Google names them.
    lead_type: Mapped[str] = mapped_column(String(24), nullable=False, default="", server_default="")
    #: NEW, ACTIVE, BOOKED, DECLINED, EXPIRED and so on, as Google names them.
    lead_status: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default="")
    charged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    category_id: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
