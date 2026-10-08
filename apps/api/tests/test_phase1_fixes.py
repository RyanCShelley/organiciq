"""Phase 1 of the decision engine review: logic bugs.

B1 Gate 0 suppressed blocking technical findings, contradicting "critical
   technical bypasses".
B2 The 30-impression demand gate hid pages that draw nothing *because* they
   are broken.
B4 Several rules claimed the same upside on one URL and the sum was counted.
B5 Gate behaviour was implicit.
"""

from __future__ import annotations

from app.models.decision import DiagnosticLayer, GrowthAction
from app.services.decision_types import LeverFinding
from app.services.lever_engine import (
    GATE_BEHAVIOUR,
    cap_per_url_impact,
    survives_tracking_gate,
)

PAGE = "https://example.com/contact"


def _finding(**over):
    base = dict(
        rule_key="k",
        lever=GrowthAction.TECHNICAL_SEO.value,
        stage=DiagnosticLayer.VISIBILITY,
        diagnosis="HTTP 503",
        recommended_action="Restore the page",
        success_metric="",
        evidence_json={},
        baseline_metrics_json={},
        impact=40.0,
        confidence=85.0,
        urgency=80.0,
        effort=45.0,
        priority_score=50.0,
        page_url=PAGE,
    )
    base.update(over)
    return LeverFinding(**base)


# --- B1 ---------------------------------------------------------------------


def _conversion(**over):
    """The only layer the gate still holds back."""
    over.setdefault("stage", DiagnosticLayer.CONVERSION)
    over.setdefault("lever", GrowthAction.CONVERSION_PATH.value)
    return _finding(**over)


def test_work_that_never_reads_the_lead_feed_survives_gate_zero():
    """A 5xx on a page is true whatever the conversion tag is doing, and so
    is a prompt nothing cites. Neither count comes from the client's tag."""
    assert survives_tracking_gate(_finding(), {PAGE}) is True
    assert survives_tracking_gate(_finding(), set()) is True
    assert survives_tracking_gate(
        _finding(stage=DiagnosticLayer.TRAFFIC, lever=GrowthAction.SERP_CTR.value),
        set(),
    ) is True


def test_a_conversion_finding_on_a_dead_page_does_not_survive():
    """No traffic last period either, so nothing is being lost right now —
    and the feed that would say otherwise is the one that went silent."""
    assert survives_tracking_gate(_conversion(), {PAGE}) is True
    assert survives_tracking_gate(_conversion(), set()) is False


def test_core_work_does_not_ride_the_exception():
    """It is never promoted anyway; letting it through widens the exception."""
    assert survives_tracking_gate(_conversion(core_work=True), {PAGE}) is False


def test_a_conversion_finding_with_no_page_cannot_survive():
    assert survives_tracking_gate(_conversion(page_url=None), {PAGE}) is False


# --- B4 ---------------------------------------------------------------------


def test_three_findings_on_one_url_cannot_sum_above_the_cap():
    rows = [
        _finding(rule_key="a", lever=GrowthAction.INTERNAL_LINKING.value, impact=30.0),
        _finding(rule_key="b", lever=GrowthAction.SERP_CTR.value, impact=20.0),
        _finding(rule_key="c", lever=GrowthAction.AI_VISIBILITY.value, impact=10.0),
    ]

    cap_per_url_impact(rows)

    assert round(sum(row.impact for row in rows), 1) == 30.0
    # Split in proportion to what each claimed.
    assert [row.impact for row in rows] == [15.0, 10.0, 5.0]


def test_the_raw_figure_is_kept_for_display():
    """"What is this worth" is honestly the uncapped number."""
    rows = [
        _finding(rule_key="a", impact=30.0),
        _finding(rule_key="b", impact=20.0),
    ]

    cap_per_url_impact(rows)

    assert rows[0].evidence_json["raw_impact"] == 30.0
    assert rows[0].evidence_json["impact_shared_with"] == 1


def test_a_single_finding_on_a_url_is_untouched():
    rows = [_finding(impact=30.0)]

    cap_per_url_impact(rows)

    assert rows[0].impact == 30.0
    assert "raw_impact" not in rows[0].evidence_json


def test_findings_on_different_urls_do_not_share_a_cap():
    rows = [
        _finding(rule_key="a", page_url="https://example.com/a", impact=30.0),
        _finding(rule_key="b", page_url="https://example.com/b", impact=30.0),
    ]

    cap_per_url_impact(rows)

    assert [row.impact for row in rows] == [30.0, 30.0]


def test_capping_rescores_so_order_reflects_the_cap():
    rows = [
        _finding(rule_key="a", impact=30.0, priority_score=99.0),
        _finding(rule_key="b", impact=20.0, priority_score=99.0),
    ]

    cap_per_url_impact(rows)

    assert rows[0].priority_score < 99.0
    assert rows[0].priority_score > rows[1].priority_score


# --- B5 ---------------------------------------------------------------------


def test_every_gate_states_what_it_suppresses():
    assert set(GATE_BEHAVIOUR) == {
        "tracking",
        "site_conversion",
        "visibility_no_traffic",
        "conversion_page",
        # Phase 3: Gate 0's two non-silence failures. Neither has a veto.
        "tracking_partial",
        "tracking_spike",
    }
    for gate, spec in GATE_BEHAVIOUR.items():
        assert spec["suppresses"], gate
        assert spec["bucket"], gate
    # Only Gate 0 suppresses, and the table has to keep saying so.
    assert GATE_BEHAVIOUR["tracking"]["suppresses"] != "nothing"
    for gate in ("site_conversion", "visibility_no_traffic", "conversion_page"):
        assert GATE_BEHAVIOUR[gate]["suppresses"] == "nothing"


# --- B2, through diagnose ---------------------------------------------------


def test_a_page_noindexed_into_silence_is_still_reported(db, client_a):
    """400 impressions to 0 after a noindex. The demand gate hid it by the
    same mechanism that damaged it."""
    from datetime import date, timedelta
    from decimal import Decimal
    from uuid import uuid4

    from app.models.crawl import FactCrawlPageSnapshot
    from app.models.gsc import FactGscPage
    from app.services.lever_engine import active_crawl_source, diagnose
    from tests.conftest import seed_required_sources

    end = date.today()
    start = end - timedelta(days=29)
    prior_day = start - timedelta(days=5)
    broken = "https://example.com/services/roofing"

    # Earned 400 impressions last period, nothing this period.
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=prior_day,
            raw_url=broken,
            normalized_url=broken,
            country="",
            device="",
            impressions=Decimal("400"),
            clicks=Decimal("40"),
            ctr=Decimal("0.1"),
            average_position=Decimal("5"),
        )
    )
    # The rest of the site still has traffic, so the engine is ready to run.
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url="https://example.com/",
            normalized_url="https://example.com",
            country="",
            device="",
            impressions=Decimal("900"),
            clicks=Decimal("90"),
            ctr=Decimal("0.1"),
            average_position=Decimal("4"),
        )
    )
    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(),
            client_id=client_a.id,
            source=active_crawl_source(),
            snapshot_date=end,
            raw_url=broken,
            normalized_url=broken,
            status_code=200,
            indexable=False,
            word_count=900,
            inbound_internal_links=5,
            inbound_editorial_links=3,
            redirect_count=0,
            in_sitemap=True,
        )
    )
    db.commit()
    seed_required_sources(db, client_a.id, end)

    result = diagnose(db, client_a, from_date=start, to_date=end)

    hit = [row for row in result.findings if row.page_url == broken]
    assert len(hit) == 1, "the page the demand gate hid"
    assert hit[0].evidence_json["audit_signal"] == "non_indexable"
    assert hit[0].evidence_json["prior_impressions"] == 400
    assert hit[0].core_work is False


def test_a_page_that_never_had_demand_is_not_resurrected(db, client_a):
    """Eligibility is prior demand, the sitemap, or a page meant to rank."""
    from datetime import date, timedelta
    from uuid import uuid4

    from app.models.crawl import FactCrawlPageSnapshot
    from app.services.lever_engine import active_crawl_source, diagnose
    from tests.conftest import seed_required_sources

    end = date.today()
    start = end - timedelta(days=29)
    junk = "https://example.com/tmp/scratch-page"

    db.add(
        FactCrawlPageSnapshot(
            id=uuid4(),
            client_id=client_a.id,
            source=active_crawl_source(),
            snapshot_date=end,
            raw_url=junk,
            normalized_url=junk,
            status_code=404,
            indexable=False,
            word_count=50,
            inbound_internal_links=0,
            inbound_editorial_links=0,
            redirect_count=0,
            in_sitemap=False,
        )
    )
    db.commit()
    seed_required_sources(db, client_a.id, end)

    result = diagnose(db, client_a, from_date=start, to_date=end)

    assert [row for row in result.findings if row.page_url == junk] == []
