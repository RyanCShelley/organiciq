from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ClientsOverviewWindowOut(BaseModel):
    from_date: date
    to_date: date
    previous_from: date
    previous_to: date
    days: int = 30


class ClientOverviewItemOut(BaseModel):
    id: UUID
    client_name: str
    slug: str
    domain: str
    status: str
    service_mode: str
    group_name: str | None = None
    plan_label: str | None = None
    business_model: Literal["lead_gen", "ecommerce", "both"] | None = None
    missing_setup: list[str] = []
    monthly_lead_goal: int | None = None
    current_lead_goal: int | None = None
    lead_goal_progress_pct: float | None = None

    # Visibility (GSC 30d)
    impressions: int | None = None
    clicks: int | None = None
    avg_position: float | None = None
    avg_position_change: float | None = None
    impressions_change_pct: float | None = None
    current_impressions_goal: int | None = None
    impressions_goal_progress_pct: float | None = None
    current_clicks_goal: int | None = None

    # Traffic (GA4 30d)
    total_sessions: int | None = None
    organic_sessions: int | None = None
    organic_change_pct: float | None = None
    current_sessions_goal: int | None = None
    sessions_goal_progress_pct: float | None = None

    # Leads (GA4 events 30d)
    leads: int | None = None
    lead_label: Literal["leads", "orders", "conversions"] = "leads"
    leads_change_pct: float | None = None

    # Freshness
    gsc_through: date | None = None
    ga4_through: date | None = None


class ClientsOverviewOut(BaseModel):
    window: ClientsOverviewWindowOut
    clients: list[ClientOverviewItemOut]
