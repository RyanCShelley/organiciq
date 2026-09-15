"""Build and optionally persist a client baseline snapshot from GA4 + calculator."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from sqlalchemy import func

from app.models.client import Client, Tier
from app.models.ga4 import FactGa4Traffic
from app.schemas import ClientUpdate
from app.services import clients as client_service
from app.services import growth_calculator
from app.services.dashboard import (
    DAYS_PER_MONTH,
    _effective_range,
    _lead_event_names,
    _lead_rate,
    _load_watermarks,
    _sum_leads,
    _sum_sessions,
)


DEFAULT_LOOKBACK_DAYS = 90
MIN_LOOKBACK_DAYS = 7
MAX_LOOKBACK_DAYS = 365


def _scale_to_monthly(value: float | int | None, period_days: int) -> float | None:
    if value is None or period_days <= 0:
        return None
    return float(value) * DAYS_PER_MONTH / period_days


def _earliest_ga4_fact(db: Session, client_id) -> date | None:
    return (
        db.query(func.min(FactGa4Traffic.date))
        .filter(FactGa4Traffic.client_id == client_id)
        .scalar()
    )


def preview_baseline_from_ga4(
    db: Session,
    client: Client,
    *,
    as_of: date | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, Any]:
    """
    Average GA4 sessions/leads over the window ending at `as_of`, scale to
    monthly, and project the goal from the tier curve.

    `as_of` defaults to the GA4 watermark; `lookback_days` defaults to 90 so the
    baseline is an average rather than whatever one month happened to look like.
    """
    lead_events = _lead_event_names(db, client.id)
    if not lead_events:
        raise ValueError(
            "Configure at least one active lead conversion definition before creating a baseline snapshot."
        )

    watermarks = _load_watermarks(db, client.id)
    ga4_wm = watermarks.get("ga4")
    if ga4_wm is None or ga4_wm.fact_through_date is None:
        raise ValueError("No validated GA4 data yet. Sync GA4 and wait for a passed watermark.")

    # Anchor the window on the requested baseline date, not on today. "Baseline
    # as of August 1" has to mean the period ending August 1 — reading back from
    # the watermark instead was the behaviour that made this unusable.
    anchor = as_of or ga4_wm.fact_through_date
    if anchor > ga4_wm.fact_through_date:
        raise ValueError(
            f"GA4 facts only run through {ga4_wm.fact_through_date.isoformat()}. "
            f"Pick a baseline date on or before that, or sync GA4 further forward."
        )

    lookback = max(MIN_LOOKBACK_DAYS, min(int(lookback_days), MAX_LOOKBACK_DAYS))
    requested_start = anchor - timedelta(days=lookback - 1)

    period = _effective_range(requested_start, anchor, ga4_wm)
    if period is None:
        raise ValueError("GA4 watermark has no usable date range.")

    period_start, period_end = period
    # Clip to facts that actually exist, so a short backfill does not get
    # averaged as if it covered the full window.
    earliest = _earliest_ga4_fact(db, client.id)
    if earliest is not None and earliest > period_start:
        period_start = earliest

    period_days = (period_end - period_start).days + 1
    if period_days < MIN_LOOKBACK_DAYS:
        raise ValueError(
            f"Only {period_days} day(s) of GA4 facts available before "
            f"{anchor.isoformat()}. Need at least {MIN_LOOKBACK_DAYS} to build a baseline."
        )

    period_sessions = _sum_sessions(db, client.id, period)
    period_leads = _sum_leads(db, client.id, lead_events, period)
    if period_sessions is None:
        raise ValueError("Could not read GA4 sessions for the baseline window.")
    if period_leads is None:
        raise ValueError("Could not read GA4 leads for the baseline window.")

    monthly_sessions = _scale_to_monthly(period_sessions, period_days)
    monthly_leads = _scale_to_monthly(period_leads, period_days)
    if monthly_sessions is None or monthly_leads is None:
        raise ValueError("Failed to scale GA4 metrics to monthly.")

    sessions_i = int(round(monthly_sessions))
    leads_i = int(round(monthly_leads))
    lead_rate = _lead_rate(period_leads, period_sessions)

    tier = db.query(Tier).filter(Tier.id == client.tier_id).one_or_none()
    plan = growth_calculator.plan_key_from_tier_name(tier.tier_name if tier else None)
    projection = growth_calculator.project_leads(
        monthly_sessions=monthly_sessions,
        monthly_leads=monthly_leads,
        plan=plan,
    )

    return {
        "ready": True,
        "window": {
            "from": period_start.isoformat(),
            "to": period_end.isoformat(),
            "period_days": period_days,
            "scaled_to_days": DAYS_PER_MONTH,
            "requested_from": requested_start.isoformat(),
            "requested_days": lookback,
            "fully_covered": period_days >= lookback,
        },
        "lead_events": lead_events,
        "tier_name": tier.tier_name if tier else None,
        "plan": projection["plan"],
        "plan_label": projection["plan_label"],
        "period_sessions": period_sessions,
        "period_leads": period_leads,
        "baseline_as_of": period_end.isoformat(),
        "baseline_monthly_sessions": sessions_i,
        "baseline_monthly_leads": leads_i,
        "baseline_lead_rate_pct": round(lead_rate, 4) if lead_rate is not None else None,
        "baseline_source": "ga4_calculator",
        "suggested_monthly_lead_goal": projection["suggested_monthly_lead_goal"],
        "goal_horizon_months": projection["goal_horizon_months"],
        "checkpoints": projection["checkpoints"],
        "disclaimer": projection["disclaimer"],
        "current_monthly_lead_goal": client.monthly_lead_goal,
    }


def build_projection_record(preview: dict[str, Any], *, generated_on: date) -> dict[str, Any]:
    """
    The projection frozen alongside the baseline.

    Checkpoints were already computed and then thrown away. They are the
    benchmarks the account is measured against, so they are stored with the
    inputs that produced them and the date they were generated — a stale set
    should be visible as stale and prompt a re-run.
    """
    return {
        "generated_on": generated_on.isoformat(),
        "baseline_as_of": preview["baseline_as_of"],
        "window": preview["window"],
        "plan": preview["plan"],
        "plan_label": preview["plan_label"],
        "goal_horizon_months": preview["goal_horizon_months"],
        "suggested_monthly_lead_goal": preview["suggested_monthly_lead_goal"],
        "checkpoints": preview["checkpoints"],
    }


def apply_baseline_from_ga4(
    db: Session,
    client: Client,
    *,
    monthly_lead_goal: int | None = None,
    notes: str | None = None,
    as_of: date | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> tuple[Client, dict[str, Any]]:
    """Persist baseline snapshot + suggested (or overridden) monthly lead goal."""
    preview = preview_baseline_from_ga4(
        db, client, as_of=as_of, lookback_days=lookback_days
    )
    goal = (
        monthly_lead_goal
        if monthly_lead_goal is not None
        else preview["suggested_monthly_lead_goal"]
    )
    note = notes
    if note is None:
        # Snapshot provenance only — plan projections belong in the calculator UI, not the dashboard.
        note = (
            f"GA4 {preview['window']['from']}→{preview['window']['to']} "
            f"({preview['window']['period_days']}d scaled to {preview['window']['scaled_to_days']}d)"
        )

    updated = client_service.update_client(
        db,
        client,
        ClientUpdate(
            baseline_as_of=date.fromisoformat(preview["baseline_as_of"]),
            baseline_period_start=date.fromisoformat(preview["window"]["from"]),
            baseline_period_end=date.fromisoformat(preview["window"]["to"]),
            baseline_monthly_sessions=preview["baseline_monthly_sessions"],
            baseline_monthly_leads=preview["baseline_monthly_leads"],
            baseline_lead_rate_pct=preview["baseline_lead_rate_pct"],
            baseline_source="ga4_calculator",
            baseline_notes=note,
            baseline_projection_json=build_projection_record(
                preview, generated_on=date.today()
            ),
            monthly_lead_goal=int(goal) if goal is not None else None,
        ),
    )
    preview["applied_monthly_lead_goal"] = updated.monthly_lead_goal
    preview["projection_generated_on"] = (
        updated.baseline_projection_json or {}
    ).get("generated_on")
    return updated, preview
