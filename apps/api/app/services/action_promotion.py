"""Promote validated findings into recommended Growth Actions."""

from __future__ import annotations

from app.models.decision import GrowthAction
from app.services.decision_impact import PageBusinessContext, SiteBusinessContext
from app.services.decision_types import LeverFinding
from app.services.page_eligibility import PageClassification

MEANINGFUL_STRATEGIC_PRIORITY = 4
MEANINGFUL_COMMERCIAL_PRIORITY = 4


def priority_band(score: float, *, high: float, medium: float) -> str:
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    if score > 0:
        return "low"
    return "none"


def _critical_override_applied(finding: LeverFinding) -> bool:
    return finding.evidence_json.get("critical_override") is True


def _has_meaningful_opportunity_signal(
    finding: LeverFinding,
    *,
    page_ctx: PageBusinessContext | None,
    classification: PageClassification | None,
    thresholds: dict[str, float | int],
) -> bool:
    evidence = finding.evidence_json
    min_impressions = int(thresholds.get("meaningful_gsc_impressions", 100))
    min_sessions = int(thresholds.get("meaningful_ga4_sessions", 10))

    if float(evidence.get("impressions") or 0) >= min_impressions:
        return True
    if page_ctx is not None and page_ctx.ga4_sessions >= min_sessions:
        return True
    if page_ctx is not None and page_ctx.ga4_leads > 0:
        return True
    if classification is not None:
        if classification.strategic_priority >= MEANINGFUL_STRATEGIC_PRIORITY:
            return True
        if classification.commercial_priority >= MEANINGFUL_COMMERCIAL_PRIORITY:
            return True
        if classification.priority_topic:
            return True
    position = evidence.get("position") or evidence.get("average_position")
    if isinstance(position, (int, float)) and 4 <= float(position) <= 20:
        return True
    if _critical_override_applied(finding):
        return True
    return False


def passes_action_eligibility(
    finding: LeverFinding,
    *,
    classification: PageClassification | None,
    page_ctx: PageBusinessContext | None,
    thresholds: dict[str, float | int],
) -> tuple[bool, str | None]:
    if finding.lever == GrowthAction.CONVERSION_PATH.value:
        return True, None
    if finding.lever == GrowthAction.STRUCTURED_DATA_AI.value:
        return True, None

    if classification is not None and not classification.eligible_for_growth_action:
        return False, classification.excluded_reason or "page_ineligible"

    if finding.lever == GrowthAction.INTERNAL_LINKING.value:
        if not _has_meaningful_opportunity_signal(
            finding,
            page_ctx=page_ctx,
            classification=classification,
            thresholds=thresholds,
        ):
            return False, "insufficient_business_signal"

    if finding.lever == GrowthAction.TECHNICAL_SEO.value:
        if _critical_override_applied(finding):
            return True, None
        if classification is not None and classification.commercial_priority >= MEANINGFUL_COMMERCIAL_PRIORITY:
            return True, None
        if _has_meaningful_opportunity_signal(
            finding,
            page_ctx=page_ctx,
            classification=classification,
            thresholds=thresholds,
        ):
            return True, None
        return False, "insufficient_business_signal"

    if finding.lever == GrowthAction.SERP_CTR.value:
        if not _has_meaningful_opportunity_signal(
            finding,
            page_ctx=page_ctx,
            classification=classification,
            thresholds=thresholds,
        ):
            return False, "insufficient_business_signal"

    return True, None


def passes_actionable_impact_gate(
    finding: LeverFinding,
    thresholds: dict[str, float | int],
) -> tuple[bool, str | None]:
    if _critical_override_applied(finding):
        return True, None

    min_impact = float(thresholds.get("minimum_actionable_impact", 25))
    min_confidence = float(thresholds.get("minimum_recommendation_confidence", 60))

    if finding.impact < min_impact:
        return False, "impact_below_threshold"
    if finding.confidence < min_confidence:
        return False, "confidence_below_threshold"
    return True, None


CRITICAL_OVERRIDE_BAND_REASON = "Critical technical override"


def promote_findings(
    findings: list[LeverFinding],
    *,
    classifications: dict[str, PageClassification],
    page_contexts: dict[str, PageBusinessContext],
    thresholds: dict[str, float | int],
) -> tuple[list[LeverFinding], list[LeverFinding]]:
    """Return (all_findings_with_metadata, recommended_actions)."""
    recommended: list[LeverFinding] = []

    high = float(thresholds.get("high_priority_threshold", 70))
    medium = float(thresholds.get("medium_priority_threshold", 50))

    for finding in sorted(findings, key=lambda row: row.priority_score, reverse=True):
        finding.priority_band = priority_band(finding.priority_score, high=high, medium=medium)
        finding.priority_band_reason = None
        finding.is_recommended_action = False
        finding.promotion_blocked_reason = None

        page_key = finding.page_url or ""
        classification = classifications.get(page_key)
        page_ctx = page_contexts.get(page_key)

        eligible, eligibility_reason = passes_action_eligibility(
            finding,
            classification=classification,
            page_ctx=page_ctx,
            thresholds=thresholds,
        )
        if not eligible:
            finding.promotion_blocked_reason = eligibility_reason
            continue

        actionable, impact_reason = passes_actionable_impact_gate(finding, thresholds)
        if not actionable:
            finding.promotion_blocked_reason = impact_reason
            continue

        finding.is_recommended_action = True
        if _critical_override_applied(finding):
            finding.priority_band = "high"
            finding.priority_band_reason = CRITICAL_OVERRIDE_BAND_REASON
        recommended.append(finding)

    return findings, recommended
