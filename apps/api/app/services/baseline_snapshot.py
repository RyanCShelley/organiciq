"""Build and optionally persist a client baseline snapshot from GA4 + calculator."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.client import Client, Tier
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


def _scale_to_monthly(value: float | int | None, period_days: int) -> float | None:
    if value is None or period_days <= 0:
        return None
    return float(value) * DAYS_PER_MONTH / period_days


def preview_baseline_from_ga4(db: Session, client: Client) -> dict[str, Any]:
    """Pull ~30d GA4 sessions/leads, scale monthly, project goal from tier curve."""
    lead_events = _lead_event_names(db, client.id)
    if not lead_events:
        raise ValueError(
            "Configure at least one active lead conversion definition before creating a baseline snapshot."
        )

    watermarks = _load_watermarks(db, client.id)
    ga4_wm = watermarks.get("ga4")
    if ga4_wm is None or ga4_wm.fact_through_date is None:
        raise ValueError("No validated GA4 data yet. Sync GA4 and wait for a passed watermark.")

    to_date = ga4_wm.fact_through_date
    from_date = to_date - timedelta(days=DAYS_PER_MONTH - 1)
    period = _effective_range(from_date, to_date, ga4_wm)
    if period is None:
        raise ValueError("GA4 watermark has no usable date range.")

    period_start, period_end = period
    period_days = (period_end - period_start).days + 1
    if period_days < 7:
        raise ValueError(
            f"Need at least 7 days of GA4 facts to build a baseline (found {period_days})."
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


def apply_baseline_from_ga4(
    db: Session,
    client: Client,
    *,
    monthly_lead_goal: int | None = None,
    notes: str | None = None,
) -> tuple[Client, dict[str, Any]]:
    """Persist baseline snapshot + suggested (or overridden) monthly lead goal."""
    preview = preview_baseline_from_ga4(db, client)
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
            baseline_monthly_sessions=preview["baseline_monthly_sessions"],
            baseline_monthly_leads=preview["baseline_monthly_leads"],
            baseline_lead_rate_pct=preview["baseline_lead_rate_pct"],
            baseline_source="ga4_calculator",
            baseline_notes=note,
            monthly_lead_goal=int(goal) if goal is not None else None,
        ),
    )
    preview["applied_monthly_lead_goal"] = updated.monthly_lead_goal
    return updated, preview
