"""OrganicIQ growth calculator — 3-pillar (Visibility, Traffic, Leads) calibrated projection model.

Calibrated against both published B2B SEO/CRO benchmarks and Organic IQ's own
12-month client cohorts:
- Visibility (GSC Impressions +15%/+30%/+45%, AI Visibility +15%/+25%/+35% rel):
  7 of 8 GSC clients met or exceeded these impression targets.
- Traffic (GA4 Sessions 0%/+5%/+10%, GSC Clicks +10%/+20%/+30%):
  Accounts for AI Overview click compression while keeping active SEO flat-to-modest.
- Leads (Hill-tapered CVR 1.20x/1.35x/1.50x with C_half=2.0%):
  Prevents unrealistic sitewide CVR inflation on high-converting sites.
- Lagged J-Curve pacing: 0% (Today) -> 10% (3m) -> 30% (6m) -> 65% (9m) -> 100% (12m).
"""

from __future__ import annotations

from typing import Literal

PlanKey = Literal["launch", "lift", "lead"]

LABELS = ("Today", "3 months", "6 months", "9 months", "12 months")
MONTHS = (0, 3, 6, 9, 12)

# Lagged J-curve weights across Today / 3 / 6 / 9 / 12 months.
J_CURVE_WEIGHTS = (0.00, 0.10, 0.30, 0.65, 1.00)

# Half-saturation starting CVR (%): at C0 == 2.0% (typical B2B median), half of raw
# multiplicative lift is achievable; higher starting CVRs taper asymptotically.
CVR_HALF_SATURATION_PCT = 2.0

# 12-month raw CVR multipliers by tier (before diminishing-returns tapering).
CVR_RAW_MULT_12MO: dict[PlanKey, float] = {
    "launch": 1.20,
    "lift": 1.35,
    "lead": 1.50,
}

# 12-month Traffic lifts (%) by tier: GA4 sessions & GSC clicks.
TRAFFIC_LIFT_12MO: dict[PlanKey, float] = {
    "launch": 0.0,
    "lift": 5.0,
    "lead": 10.0,
}

TRAFFIC_CLICKS_LIFT_12MO: dict[PlanKey, float] = {
    "launch": 10.0,
    "lift": 20.0,
    "lead": 30.0,
}

# 12-month Visibility lifts (%) by tier: GSC impressions & relative AI visibility.
VISIBILITY_IMPRESSIONS_LIFT_12MO: dict[PlanKey, float] = {
    "launch": 15.0,
    "lift": 30.0,
    "lead": 45.0,
}

AI_VISIBILITY_REL_LIFT_12MO: dict[PlanKey, float] = {
    "launch": 15.0,
    "lift": 25.0,
    "lead": 35.0,
}

AI_VISIBILITY_FLOOR_PTS_12MO: dict[PlanKey, float] = {
    "launch": 5.0,
    "lift": 8.0,
    "lead": 12.0,
}

PLAN_DISPLAY = {"launch": "Launch", "lift": "Lift", "lead": "Lead"}


def _weight_for_month(month: int) -> float:
    if month in MONTHS:
        return J_CURVE_WEIGHTS[MONTHS.index(month)]
    return max(0.0, min(month / 12.0, 1.0))


def traffic_mult(month: int, plan: PlanKey = "launch") -> float:
    return 1.0 + (TRAFFIC_LIFT_12MO[plan] / 100.0) * _weight_for_month(month)


def visibility_impressions_mult(month: int, plan: PlanKey = "launch") -> float:
    return 1.0 + (VISIBILITY_IMPRESSIONS_LIFT_12MO[plan] / 100.0) * _weight_for_month(month)


def visibility_clicks_mult(month: int, plan: PlanKey = "launch") -> float:
    return 1.0 + (TRAFFIC_CLICKS_LIFT_12MO[plan] / 100.0) * _weight_for_month(month)


def effective_cvr_mult(month: int, plan: PlanKey, baseline_cvr_pct: float) -> float:
    """Apply J-curve pacing and diminishing returns so high starting CVR tapers realistic lift."""
    raw_lift = max(CVR_RAW_MULT_12MO[plan] - 1.0, 0.0) * _weight_for_month(month)
    dampen = 1.0 / (1.0 + max(baseline_cvr_pct, 0.0) / CVR_HALF_SATURATION_PCT)
    return 1.0 + raw_lift * dampen


def plan_key_from_tier_name(tier_name: str | None) -> PlanKey:
    """Map OrganicIQ tier catalog names onto calculator plans."""
    normalized = (tier_name or "").strip().lower()
    if normalized == "lift":
        return "lift"
    if normalized in {"lead", "enterprise"}:
        return "lead"
    # Launch + Legacy (+ unknown) use Launch curve
    return "launch"


def project_leads(
    *,
    monthly_sessions: float,
    monthly_leads: float,
    plan: PlanKey,
    monthly_gsc_impressions: float | None = None,
    monthly_gsc_clicks: float | None = None,
    ai_visibility_pct: float | None = None,
) -> dict:
    """Project Visibility (impressions, AI %), Traffic (sessions, clicks), CVR, and Leads."""
    traffic0 = max(float(monthly_sessions), 0.0)
    leads0 = max(float(monthly_leads), 0.0)
    cvr0 = (leads0 / traffic0) * 100 if traffic0 > 0 else 0.0
    impr0 = max(float(monthly_gsc_impressions), 0.0) if monthly_gsc_impressions is not None else None
    clicks0 = max(float(monthly_gsc_clicks), 0.0) if monthly_gsc_clicks is not None else None
    ai0 = max(0.0, min(float(ai_visibility_pct), 100.0)) if ai_visibility_pct is not None else None

    checkpoints: list[dict] = []
    for i, month in enumerate(MONTHS):
        w = _weight_for_month(month)
        traffic_proj = traffic0 * traffic_mult(month, plan)
        cvr_proj = cvr0 * effective_cvr_mult(month, plan, cvr0)
        leads_proj = traffic_proj * (cvr_proj / 100)
        if month > 0:
            leads_proj = max(leads_proj, leads0)
        impr_proj = round(impr0 * visibility_impressions_mult(month, plan), 1) if impr0 is not None else None
        clicks_proj = round(clicks0 * visibility_clicks_mult(month, plan), 1) if clicks0 is not None else None
        if ai0 is not None:
            ai_gain = max(ai0 * (AI_VISIBILITY_REL_LIFT_12MO[plan] / 100.0), AI_VISIBILITY_FLOOR_PTS_12MO[plan]) * w
            ai_proj = round(min(85.0, ai0 + ai_gain), 1)
        else:
            ai_proj = None
        checkpoints.append(
            {
                "label": LABELS[i],
                "month": month,
                "monthly_sessions": round(traffic_proj, 2),
                "lead_rate_pct": round(cvr_proj, 4),
                "monthly_leads": round(leads_proj, 2),
                "monthly_gsc_impressions": impr_proj,
                "monthly_gsc_clicks": clicks_proj,
                "ai_visibility_pct": ai_proj,
            }
        )

    goal_leads_12 = max(int(round(checkpoints[-1]["monthly_leads"])), int(round(leads0)), 0)
    goal_traffic_12 = max(int(round(checkpoints[-1]["monthly_sessions"])), int(round(traffic0)), 0)
    goal_impr_12 = (
        max(int(round(checkpoints[-1]["monthly_gsc_impressions"])), int(round(impr0)), 0)
        if impr0 is not None and checkpoints[-1]["monthly_gsc_impressions"] is not None
        else None
    )
    goal_clicks_12 = (
        max(int(round(checkpoints[-1]["monthly_gsc_clicks"])), int(round(clicks0)), 0)
        if clicks0 is not None and checkpoints[-1]["monthly_gsc_clicks"] is not None
        else None
    )
    goal_ai_12 = checkpoints[-1]["ai_visibility_pct"]

    return {
        "plan": plan,
        "plan_label": PLAN_DISPLAY[plan],
        "baseline_monthly_sessions": round(traffic0, 2),
        "baseline_monthly_leads": round(leads0, 2),
        "baseline_lead_rate_pct": round(cvr0, 4),
        "baseline_monthly_gsc_impressions": round(impr0, 1) if impr0 is not None else None,
        "baseline_monthly_gsc_clicks": round(clicks0, 1) if clicks0 is not None else None,
        "baseline_ai_visibility_pct": round(ai0, 1) if ai0 is not None else None,
        "suggested_monthly_lead_goal": goal_leads_12,
        "suggested_monthly_traffic_goal": goal_traffic_12,
        "suggested_monthly_visibility_impressions_goal": goal_impr_12,
        "suggested_monthly_visibility_clicks_goal": goal_clicks_12,
        "suggested_ai_visibility_pct_goal": goal_ai_12,
        "goal_horizon_months": 12,
        "checkpoints": checkpoints,
        "disclaimer": (
            "Lagged J-curve Visibility & Traffic model with diminishing-returns CVR, calibrated to Organic IQ 12-month client cohorts; "
            "not a guarantee. Actual results vary by industry, starting point, market, and execution."
        ),
    }
