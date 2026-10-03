from app.decisions.thresholds import merge_thresholds
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


def test_advisory_audit_signal_stays_in_findings_not_shortlist():
    from app.models.decision import DiagnosticLayer

    url = "https://example.com/blog/useful-post"
    findings = [
        LeverFinding(
            rule_key=f"technical:{url}",
            lever=GrowthAction.TECHNICAL_SEO.value,
            stage=DiagnosticLayer.VISIBILITY,
            diagnosis="Duplicate meta",
            recommended_action="Fix meta",
            success_metric="Unique meta",
            evidence_json={
                "impressions": 500,
                "audit_signal": "duplicate_meta",
                "issue_code": "title_duplicate",
                "promotion_class": "advisory",
                "critical_override": False,
            },
            baseline_metrics_json={},
            impact=40,
            confidence=85,
            urgency=80,
            effort=45,
            priority_score=50,
            page_url=url,
        )
    ]
    classifications = {url: classify_page_url(url)}
    all_findings, actions = promote_findings(
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
    assert len(all_findings) == 1
    assert len(actions) == 0
    assert findings[0].promotion_blocked_reason == "advisory_audit_signal"


def test_a_critical_fault_on_a_page_worth_nothing_is_not_a_recommendation():
    """The override was skipping the impact gate outright.

    That put six canonical findings worth 0.0 leads at the top of one
    client's queue as High-priority recommendations. A broken page with
    nothing behind it is still a page with nothing behind it; the override
    lowers the bar, it does not remove it.
    """
    from app.models.decision import DiagnosticLayer

    finding = LeverFinding(
        rule_key="technical:https://example.com/industries/legal",
        lever=GrowthAction.TECHNICAL_SEO.value,
        stage=DiagnosticLayer.VISIBILITY,
        diagnosis="Canonical points somewhere unusable",
        recommended_action="Point the canonical at this URL",
        success_metric="Issue clears in the next audit",
        evidence_json={
            "impressions": 415,
            "critical_override": True,
            "critical_override_reason": "non_indexable_with_demand",
        },
        baseline_metrics_json={},
        impact=0.2,
        confidence=85,
        urgency=90,
        effort=45,
        priority_score=0.4,
    )
    all_findings, recommended = promote_findings(
        [finding],
        classifications={},
        page_contexts={},
        thresholds=merge_thresholds(None),
    )
    assert recommended == []
    assert all_findings[0].promotion_blocked_reason is not None


def test_critical_override_promotes_with_high_band_despite_a_low_score():
    """A real block on a page with demand still outranks its own score.

    The impact here clears `critical_override_min_impact`; what the override
    is doing is lifting a finding whose *priority score* would otherwise
    bury it under content ideas.
    """
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
            impact=14.0,
            confidence=85,
            urgency=90,
            effort=45,
            priority_score=18.6,
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
    assert actions[0].priority_score == 18.6
    assert actions[0].priority_band == "high"
    assert actions[0].priority_band_reason == "Critical technical override"
