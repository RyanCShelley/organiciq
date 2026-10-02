"""How much a finding's number can be trusted.

Confidence was a constant per lever — 85 for technical, 70 for conversion
path — so it said how much that *kind* of rule is generally trusted and nothing
about the evidence in front of it. Every value sat above the promotion gate of
60, which made that gate dead code: it had never blocked anything, and a
finding resting on one page's measured leads outranked nothing resting on a
third-party volume estimate.

Three things move the score, all downward, and the lever's own constant is the
ceiling: a rule cannot become more trustworthy than its kind allows, however
clean one page's data happens to be.

Applying it is off by default. Lowering confidence under an unchanged gate
silently stops promoting findings, and which findings those are has to be
looked at on real clients before the bar moves. `data_driven_confidence` is
recorded on every finding either way, so the distribution can be measured
without changing anyone's recommendations first.
"""

from __future__ import annotations

from typing import Any, Mapping

#: Where the number came from. Deliberately gentler than the impact haircut in
#: `normalize_business_impact`, which already discounts the estimate itself:
#: charging the full penalty in both places would punish one uncertainty twice,
#: once on the size of the prize and again on the right to be considered.
TIER_KEYS: dict[str, str] = {
    "high": "confidence_tier_high",
    "medium": "confidence_tier_medium",
    "low": "confidence_tier_low",
}


def data_confidence(
    lever_confidence: float,
    evidence: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    *,
    data_age_days: int | None = None,
) -> float:
    """Confidence for one finding, never above its lever's own ceiling."""
    score = float(lever_confidence)

    tier = str(evidence.get("data_confidence") or "high")
    key = TIER_KEYS.get(tier, TIER_KEYS["low"])
    score *= float(thresholds.get(key, 1.0))

    if _thin_evidence(evidence, thresholds):
        score *= float(thresholds.get("confidence_small_sample_factor", 1.0))

    stale_after = float(thresholds.get("confidence_stale_after_days", 14))
    if data_age_days is not None and data_age_days > stale_after:
        score *= float(thresholds.get("confidence_stale_factor", 1.0))

    return round(min(score, float(lever_confidence)), 1)


def _thin_evidence(evidence: Mapping[str, Any], thresholds: Mapping[str, Any]) -> bool:
    """Whether the finding rests on too little to be more than a guess.

    Leads first, because a rule that counts leads has already done the harder
    inference; impressions only stand in when no lead estimate was made. A
    finding carrying neither is not thin, it is simply not of this shape, and
    penalising it for that would hit every technical check.
    """
    leads = evidence.get("estimated_incremental_leads")
    if leads is None:
        leads = evidence.get("estimated_leads_at_risk")
    if leads is not None:
        return float(leads) < float(thresholds.get("confidence_min_sample_leads", 0))

    impressions = evidence.get("impressions")
    if impressions is None:
        impressions = evidence.get("prior_impressions")
    if impressions is not None:
        return float(impressions) < float(
            thresholds.get("confidence_min_sample_impressions", 0)
        )
    return False
