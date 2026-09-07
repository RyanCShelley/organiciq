from app.services.decision_impact import (
    SiteBusinessContext,
    assess_technical_severity,
    downstream_lead_opportunity,
    fallback_visibility_impact,
    normalize_business_impact,
    score_conversion_impact,
    score_serp_ctr_impact,
    score_technical_impact,
)
from app.services.page_eligibility import classify_page_url


def _site(*, leads: int = 10, sessions: float = 1000, rate: float | None = 1.0, goal: int | None = 25) -> SiteBusinessContext:
    return SiteBusinessContext(
        site_lead_rate_pct=rate,
        period_sessions=sessions,
        period_leads=leads,
        period_lead_goal=goal,
        p90_page_sessions=200,
    )


def test_downstream_lead_opportunity_chain():
    assert downstream_lead_opportunity(100, 2.0) == 2.0


def test_normalize_incremental_leads_is_proportional():
    site = _site(leads=20, goal=25)
    impact, meta = normalize_business_impact(
        site=site,
        estimated_incremental_leads=0.36,
        data_confidence="medium",
    )
    assert meta["impact_normalization_basis"] == "incremental_leads"
    assert impact < 20
    assert impact > 0


def test_serp_ctr_does_not_inflate_impact_with_traffic_floor():
    site = _site(leads=20, rate=1.44, goal=25)
    impact, evidence = score_serp_ctr_impact(
        recoverable_clicks=25.1,
        page_ctx=None,
        site=site,
        clicks=2,
        average_position=4.8,
    )
    assert evidence["estimated_incremental_leads"] == round(25.1 * 1.44 / 100, 2)
    assert impact < 25
    assert "traffic_fallback_score" not in evidence


def test_meaningful_incremental_leads_can_reach_high_impact():
    site = _site(leads=20, goal=25)
    impact, _ = normalize_business_impact(
        site=site,
        estimated_incremental_leads=6.0,
        data_confidence="high",
    )
    assert impact >= 90


def test_visibility_fallback_caps_without_lead_rate():
    assessment = score_technical_impact(
        impressions=5000,
        clicks=2,
        average_position=14,
        indexable=True,
        status_code=200,
        canonicalized_elsewhere=False,
        page_ctx=None,
        site=_site(rate=None, leads=0, goal=None),
    )
    assert assessment.evidence["impact_normalization_basis"] == "upstream_fallback"
    assert assessment.impact <= 35
    assert assessment.severity < 100


def test_non_indexable_priority_commercial_separates_impact_and_severity():
    url = "https://smamarketing.net/services/sem"
    classification = classify_page_url(url)
    assessment = score_technical_impact(
        impressions=126,
        clicks=0,
        average_position=18,
        indexable=False,
        status_code=200,
        canonicalized_elsewhere=False,
        page_ctx=None,
        site=_site(rate=0.0, leads=0, sessions=500, goal=25),
        classification=classification,
    )
    assert assessment.severity == 100.0
    assert assessment.critical_override is True
    assert assessment.impact < 80
    assert "indexation_unlock_floor" not in assessment.evidence


def test_assess_technical_severity_for_commercial_noindex():
    classification = classify_page_url("https://example.com/services/sem")
    severity, critical_override, reason = assess_technical_severity(
        indexable=False,
        status_code=200,
        canonicalized_elsewhere=False,
        classification=classification,
    )
    assert severity == 100.0
    assert critical_override is True
    assert reason == "unexpected_noindex_on_priority_commercial_page"


def test_conversion_uses_leads_at_risk():
    site = _site(leads=10, sessions=1000, rate=1.0)
    impact, evidence = score_conversion_impact(
        sessions_current=500,
        current_rate=0.5,
        previous_rate=2.0,
        site=site,
    )
    assert evidence["leads_at_risk"] == 7.5
    assert impact > 0
    assert evidence["impact_normalization_basis"] == "leads_at_risk"


def test_fallback_visibility_uses_clicks_not_impressions():
    score = fallback_visibility_impact(clicks=2, average_position=14)
    assert score < 20
