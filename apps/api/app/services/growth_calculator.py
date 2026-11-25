"""OrganicIQ growth calculator — Launch / Lift / Lead CVR projection curves.

Curves are mean CVR multipliers from pooled Launch-relevant clients, tapered by a
diminishing-returns (Hill-style) factor based on starting CVR so sites that already
convert well do not receive unrealistic multiplicative CVR targets. Traffic
assumptions reflect AI Overview click erosion offset by each tier's SEO scope.
"""

from __future__ import annotations

from typing import Literal

PlanKey = Literal["launch", "lift", "lead"]

LABELS = ("Today", "3 months", "6 months", "9 months", "12 months")
MONTHS = (0, 3, 6, 9, 12)

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

# Net 12-month traffic change (%) by tier: AI Overview click erosion (-12.8% baseline)
# is progressively offset by commercial content, GEO, and CTR optimization on Lift/Lead.
TRAFFIC_CHANGE_12MO: dict[PlanKey, float] = {
    "launch": -12.8,
    "lift": -5.0,
    "lead": 0.0,
}

PLAN_DISPLAY = {"launch": "Launch", "lift": "Lift", "lead": "Lead"}


def traffic_mult(month: int, plan: PlanKey = "launch") -> float:
    return 1 + (TRAFFIC_CHANGE_12MO[plan] / 100) * (month / 12)


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
) -> dict:
    """Project traffic, CVR, and leads at Today / 3 / 6 / 9 / 12 months."""
    traffic0 = max(float(monthly_sessions), 0.0)
    leads0 = max(float(monthly_leads), 0.0)
    cvr0 = (leads0 / traffic0) * 100 if traffic0 > 0 else 0.0
    mult = CVR_MULT[plan]

    checkpoints: list[dict] = []
    for i, month in enumerate(MONTHS):
        traffic_proj = traffic0 * traffic_mult(month, plan)
        cvr_proj = cvr0 * effective_cvr_mult(mult[i], cvr0)
        leads_proj = traffic_proj * (cvr_proj / 100)
        if month > 0:
            leads_proj = max(leads_proj, leads0)
        checkpoints.append(
            {
                "label": LABELS[i],
                "month": month,
                "monthly_sessions": round(traffic_proj, 2),
                "lead_rate_pct": round(cvr_proj, 4),
                "monthly_leads": round(leads_proj, 2),
            }
        )

    goal_12 = max(int(round(checkpoints[-1]["monthly_leads"])), int(round(leads0)))
    if goal_12 < 0:
        goal_12 = 0

    return {
        "plan": plan,
        "plan_label": PLAN_DISPLAY[plan],
        "baseline_monthly_sessions": round(traffic0, 2),
        "baseline_monthly_leads": round(leads0, 2),
        "baseline_lead_rate_pct": round(cvr0, 4),
        "suggested_monthly_lead_goal": goal_12,
        "goal_horizon_months": 12,
        "checkpoints": checkpoints,
        "disclaimer": (
            "Projection uses diminishing-returns CVR curves and tier-adjusted traffic assumptions, not a guarantee. "
            "Actual results vary by industry, starting point, market, and execution."
        ),
    }
