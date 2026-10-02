"""Phase 5: effort as a size, and what an impact number actually means.

S2 is not here. It is conditional — "if a persona or lead-value field
exists" — and none does, on the client or on any conversion definition.
Inventing a persona model to multiply by 1.0 would add a concept the product
does not have.
"""

from __future__ import annotations

from app.decisions.effort import (
    LARGE,
    MEDIUM,
    SMALL,
    effort_class,
    ranking_score,
)
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


def test_a_title_edit_is_small_and_a_new_cluster_page_is_large():
    assert effort_class("serp_ctr", {"audit_signal": "title_missing"}) == SMALL
    assert effort_class("technical_seo", {"audit_signal": "missing_schema"}) == MEDIUM
    assert effort_class("structured_data_ai", {"audit_signal": "content_cluster"}) == LARGE


def test_a_rule_with_no_size_of_its_own_falls_back_to_its_lever():
    assert effort_class("internal_linking", {}) == SMALL
    assert effort_class("technical_seo", {}) == MEDIUM
    assert effort_class("something_new", {}) == MEDIUM


def test_the_cheaper_of_two_equal_findings_ranks_higher():
    cheap = ranking_score(impact=60, confidence=80, effort=SMALL, thresholds=LIMITS)
    dear = ranking_score(impact=60, confidence=80, effort=LARGE, thresholds=LIMITS)
    assert cheap > dear
    assert cheap == 48.0
    assert dear == 19.2


def test_a_big_enough_prize_still_beats_a_cheap_one():
    """Effort re-orders; it does not let a trivial win outrank a real one."""
    big_and_slow = ranking_score(impact=100, confidence=80, effort=LARGE, thresholds=LIMITS)
    small_and_quick = ranking_score(impact=20, confidence=80, effort=SMALL, thresholds=LIMITS)
    assert big_and_slow > small_and_quick


def test_the_weights_are_tunable_without_a_deploy():
    patient = merge_thresholds({"effort_weight_large": 1.0})
    assert ranking_score(
        impact=60, confidence=80, effort=LARGE, thresholds=patient
    ) == ranking_score(impact=60, confidence=80, effort=SMALL, thresholds=LIMITS)


def test_diagnose_sizes_every_finding_and_orders_the_head_by_cost(db, client_a):
    """The re-order has to reach the queue, not just exist as a function."""
    from datetime import timedelta

    from tests.test_phase4_rules import DEAD, END, START, _crawled, _linked, _minimal_site, _run

    _minimal_site(db, client_a)
    # A mix of sizes: an orphan page (small) and a dead linked URL (small),
    # alongside whatever the page itself turns up.
    _crawled(db, client_a.id, "https://example.com/guide", status=200, inbound=0)
    _crawled(db, client_a.id, DEAD, status=404)
    _linked(db, client_a.id, DEAD, 9)
    result = _run(db, client_a)
    assert result.findings

    for finding in result.findings:
        assert finding.evidence_json["effort_class"] in {SMALL, MEDIUM, LARGE}
        assert finding.evidence_json["ranking_score"] >= 0

    top_n = LIMITS["effort_reorder_top_n"]
    head = [row.evidence_json["ranking_score"] for row in result.findings[:top_n]]
    assert head == sorted(head, reverse=True)

    assert END > START - timedelta(days=1)
