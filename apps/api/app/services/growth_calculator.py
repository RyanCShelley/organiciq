"""OrganicIQ growth calculator — 3-pillar (Visibility, Traffic, Leads) empirical projection model.

Grounded in published B2B SEO & CRO benchmarks:
- Lagged J-Curve timing (First Page Sage / Semrush / Ahrefs): months 1–3 focus on
  technical foundation & indexing (~10% of Year-1 lift), month 6 hits the Page 1–2
  inflection (~30%), and months 9–12 compound (~65% -> 100%).
- Hill-style diminishing returns on CVR (CXL / VWO / Unbounce): sites starting near
  or above the ~2% B2B median taper asymptotically instead of multiplying blindly.
- Tier-aware Visibility & Traffic lifts: active commercial content, GEO/AI citations,
  and CTR optimization on Lift/Lead offset AI Overview informational click erosion
  (Seer Interactive / Ahrefs / Pew Research).
"""

from __future__ import annotations

from typing import Literal

PlanKey = Literal["launch", "lift", "lead"]

LABELS = ("Today", "3 months", "6 months", "9 months", "12 months")
MONTHS = (0, 3, 6, 9, 12)

# Lagged J-curve weights across Today / 3 / 6 / 9 / 12 months.
J_CURVE_WEIGHTS = (0.00, 0.10, 0.30, 0.65, 1.00)

# Q1=1.00, Q2=1.09, Q3=1.15, Q4=1.60; month 9 interpolated midpoint of Q3→Q4.
LAUNCH_CURVE = (1.000, 1.092, 1.148, 1.372, 1.596)

CVR_MULT: dict[PlanKey, tuple[float, ...]] = {
    "launch": LAUNCH_CURVE,
    "lift": tuple(1 + (m - 1) * 1.5 for m in LAUNCH_CURVE),
    "lead": tuple(1 + (m - 1) * 2.1 for m in LAUNCH_CURVE),
}

# Half-saturation starting CVR (%): at C0 == 2.0% (typical B2B median), half of raw
# multiplicative lift is achievable; higher starting CVRs taper asymptotically.
CVR_HALF_SATURATION_PCT = 2.0

# Net 12-month Traffic (sessions) and Visibility (GSC clicks, AI visibility pts) lifts by tier.
TRAFFIC_LIFT_12MO: dict[PlanKey, float] = {
    "launch": 5.0,
    "lift": 12.0,
    "lead": 20.0,
}

VISIBILITY_CLICKS_LIFT_12MO: dict[PlanKey, float] = {
    "launch": 8.0,
    "lift": 18.0,
    "lead": 30.0,
}

AI_VISIBILITY_LIFT_PTS_12MO: dict[PlanKey, float] = {
    "launch": 5.0,
    "lift": 10.0,
    "lead": 15.0,
}

PLAN_DISPLAY = {"launch": "Launch", "lift": "Lift", "lead": "Lead"}


def _weight_for_month(month: int) -> float:
    if month in MONTHS:
        return J_CURVE_WEIGHTS[MONTHS.index(month)]
    return max(0.0, min(month / 12.0, 1.0))


def traffic_mult(month: int, plan: PlanKey = "launch") -> float:
    return 1.0 + (TRAFFIC_LIFT_12MO[plan] / 100.0) * _weight_for_month(month)


def visibility_clicks_mult(month: int, plan: PlanKey = "launch") -> float:
    return 1.0 + (VISIBILITY_CLICKS_LIFT_12MO[plan] / 100.0) * _weight_for_month(month)


def effective_cvr_mult(raw_mult: float, baseline_cvr_pct: float) -> float:
    """Apply diminishing returns so high starting CVR tapers realistic lift."""
    lift = max(raw_mult - 1.0, 0.0)
    dampen = 1.0 / (1.0 + max(baseline_cvr_pct, 0.0) / CVR_HALF_SATURATION_PCT)
    return 1.0 + lift * dampen


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
    monthly_gsc_clicks: float | None = None,
    ai_visibility_pct: float | None = None,
) -> dict:
    """Project Visibility, Traffic, CVR, and Leads at Today / 3 / 6 / 9 / 12 months."""
    traffic0 = max(float(monthly_sessions), 0.0)
    leads0 = max(float(monthly_leads), 0.0)
    cvr0 = (leads0 / traffic0) * 100 if traffic0 > 0 else 0.0
    clicks0 = max(float(monthly_gsc_clicks), 0.0) if monthly_gsc_clicks is not None else None
    ai0 = max(0.0, min(float(ai_visibility_pct), 100.0)) if ai_visibility_pct is not None else None
    mult = CVR_MULT[plan]

    checkpoints: list[dict] = []
    for i, month in enumerate(MONTHS):
        w = _weight_for_month(month)
        traffic_proj = traffic0 * traffic_mult(month, plan)
        cvr_proj = cvr0 * effective_cvr_mult(mult[i], cvr0)
        leads_proj = traffic_proj * (cvr_proj / 100)
        if month > 0:
            leads_proj = max(leads_proj, leads0)
        clicks_proj = round(clicks0 * visibility_clicks_mult(month, plan), 1) if clicks0 is not None else None
        ai_proj = round(min(85.0, ai0 + AI_VISIBILITY_LIFT_PTS_12MO[plan] * w), 1) if ai0 is not None else None
        checkpoints.append(
            {
                "label": LABELS[i],
                "month": month,
                "monthly_sessions": round(traffic_proj, 2),
                "lead_rate_pct": round(cvr_proj, 4),
                "monthly_leads": round(leads_proj, 2),
                "monthly_gsc_clicks": clicks_proj,
                "ai_visibility_pct": ai_proj,
            }
        )

    goal_leads_12 = max(int(round(checkpoints[-1]["monthly_leads"])), int(round(leads0)), 0)
    goal_traffic_12 = max(int(round(checkpoints[-1]["monthly_sessions"])), int(round(traffic0)), 0)
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
        "baseline_monthly_gsc_clicks": round(clicks0, 1) if clicks0 is not None else None,
        "baseline_ai_visibility_pct": round(ai0, 1) if ai0 is not None else None,
        "suggested_monthly_lead_goal": goal_leads_12,
        "suggested_monthly_traffic_goal": goal_traffic_12,
        "suggested_monthly_visibility_clicks_goal": goal_clicks_12,
        "suggested_ai_visibility_pct_goal": goal_ai_12,
        "goal_horizon_months": 12,
        "checkpoints": checkpoints,
        "disclaimer": (
            "Lagged J-curve Visibility & Traffic model with diminishing-returns CVR, grounded in B2B SEO/CRO benchmarks; "
            "not a guarantee. Actual results vary by industry, starting point, market, and execution."
        ),
    }
