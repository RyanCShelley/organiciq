from app.models.decision import GrowthAction
from app.services.action_promotion import promote_findings
from app.services.decision_types import LeverFinding
from app.services.page_eligibility import classify_page_url


def _finding(*, lever: str, impact: float, page_url: str, impressions: int = 200) -> LeverFinding:
    from app.models.decision import DiagnosticLayer

    return LeverFinding(
        rule_key=f"{lever}:{page_url}",
        lever=lever,
        stage=DiagnosticLayer.VISIBILITY,
        diagnosis="test",
        recommended_action="act",
        success_metric="metric",
        evidence_json={"impressions": impressions, "position": 12},
        baseline_metrics_json={},
        impact=impact,
        confidence=75,
        urgency=55,
        effort=30,
        priority_score=50,
        page_url=page_url,
    )


def test_low_impact_finding_not_promoted():
    url = "https://example.com/blog/useful-post"
    findings = [
        _finding(
            lever=GrowthAction.INTERNAL_LINKING.value,
            impact=5,
            page_url=url,
        )
    ]
    classifications = {url: classify_page_url(url)}
    _, actions = promote_findings(
        findings,
        classifications=classifications,
        page_contexts={},
        thresholds={
            "minimum_actionable_impact": 25,
            "minimum_recommendation_confidence": 60,
            "high_priority_threshold": 70,
            "medium_priority_threshold": 50,
            "meaningful_gsc_impressions": 100,
            "meaningful_ga4_sessions": 10,
        },
    )
    assert len(actions) == 0
    assert findings[0].promotion_blocked_reason == "impact_below_threshold"


def test_ineligible_utility_page_not_promoted():
    url = "https://example.com/opt-out-preferences"
    findings = [
        _finding(
            lever=GrowthAction.INTERNAL_LINKING.value,
            impact=80,
            page_url=url,
        )
    ]
    classifications = {url: classify_page_url(url)}
    _, actions = promote_findings(
        findings,
        classifications=classifications,
        page_contexts={},
        thresholds={
            "minimum_actionable_impact": 25,
            "minimum_recommendation_confidence": 60,
            "high_priority_threshold": 70,
            "medium_priority_threshold": 50,
            "meaningful_gsc_impressions": 100,
            "meaningful_ga4_sessions": 10,
        },
    )
    assert len(actions) == 0
    assert findings[0].promotion_blocked_reason == "opt_out_preferences"


def test_critical_override_promotes_with_high_band_without_score_floor():
    from app.models.decision import DiagnosticLayer

    url = "https://example.com/services/sem"
    findings = [
        LeverFinding(
            rule_key=f"technical:{url}",
            lever=GrowthAction.TECHNICAL_SEO.value,
            stage=DiagnosticLayer.VISIBILITY,
            diagnosis="Non-indexable page with demand",
            recommended_action="Resolve indexation issues",
            success_metric="Page becomes indexable",
            evidence_json={
                "impressions": 500,
                "critical_override": True,
                "critical_override_reason": "non_indexable_with_demand",
            },
            baseline_metrics_json={},
            impact=4.6,
            confidence=85,
            urgency=90,
            effort=45,
            priority_score=10.1,
            page_url=url,
        )
    ]
    classifications = {url: classify_page_url(url)}
    _, actions = promote_findings(
        findings,
        classifications=classifications,
        page_contexts={},
        thresholds={
            "minimum_actionable_impact": 25,
            "minimum_recommendation_confidence": 60,
            "high_priority_threshold": 70,
            "medium_priority_threshold": 50,
            "meaningful_gsc_impressions": 100,
            "meaningful_ga4_sessions": 10,
        },
    )
    assert len(actions) == 1
    assert actions[0].priority_score == 10.1
    assert actions[0].priority_band == "high"
    assert actions[0].priority_band_reason == "Critical technical override"
