"""Phase 5: effort as a size, and what an impact number actually means.

S2 is not here. It is conditional — "if a persona or lead-value field
exists" — and none does, on the client or on any conversion definition.
Inventing a persona model to multiply by 1.0 would add a concept the product
does not have.
"""

from __future__ import annotations

from app.decisions.thresholds import merge_thresholds
from app.services.decision_impact import (
    LEAD_IMPACT_REFERENCE_FRACTION,
    SiteBusinessContext,
    business_impact_reference_leads,
    normalize_business_impact,
)

LIMITS = merge_thresholds(None)


def _site(goal: int) -> SiteBusinessContext:
    return SiteBusinessContext(
        period_lead_goal=goal,
        period_leads=0,
        site_lead_rate_pct=0.0,
        period_sessions=0.0,
        p90_page_sessions=0.0,
    )


# ── S3: the units ──


def test_an_impact_of_25_on_a_20_lead_goal_is_1_25_leads():
    """Impact is a share of a quarter of the goal, not of the goal.

    The two readings differ by a factor of four, and the promotion floor of
    25 means "worth a sixteenth of the month", not "a quarter of it".
    """
    site = _site(20)
    assert business_impact_reference_leads(site) == 5.0

    impact, _ = normalize_business_impact(
        site=site, estimated_incremental_leads=1.25, data_confidence="high"
    )
    assert impact == 25.0

    # 6.25% of the goal, which is what 25% of 25% comes to.
    assert 1.25 / 20 == LEAD_IMPACT_REFERENCE_FRACTION * 0.25


def test_the_scale_is_linear_in_leads():
    site = _site(20)
    one, _ = normalize_business_impact(
        site=site, estimated_incremental_leads=1.25, data_confidence="high"
    )
    two, _ = normalize_business_impact(
        site=site, estimated_incremental_leads=2.5, data_confidence="high"
    )
    assert two == one * 2


# ── S1: effort ──
