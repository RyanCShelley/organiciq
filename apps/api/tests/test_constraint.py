"""Which of the three is holding a client back this month.

The engine had ten actions and no judgement, so it offered SMA twenty-five
prompt gaps when its actual problem was that it had relaunched and lost its
rankings. This picks one answer first.

The ladder is the argument: visibility earns traffic earns leads, so a broken
rung upstream takes the month even when a lower rung scores worse. A conversion
fix on a page nobody can find is an hour spent at the wrong end of the funnel.
"""

from __future__ import annotations

import pytest

from app.decisions.constraint import (
    ConversionSignals,
    Layer,
    TrafficSignals,
    VisibilitySignals,
    assess_conversion,
    assess_traffic,
    assess_visibility,
    select_constraint,
)
from app.decisions.thresholds import merge_thresholds

LIMITS = merge_thresholds(None)
TOP10 = LIMITS["constraint_visibility_floor_top10_share"]
AI_PCT = LIMITS["constraint_visibility_floor_ai_citation_pct"]
TRAFFIC = LIMITS["constraint_traffic_floor_ratio"]
CONVERSION = LIMITS["constraint_conversion_floor_ratio"]
MIN_IMPRESSIONS = LIMITS["constraint_traffic_min_impressions"]


def _vis(**kw):
    return assess_visibility(
        VisibilitySignals(**kw), top10_floor=TOP10, ai_citation_floor_pct=AI_PCT
    )


def _traf(**kw):
    return assess_traffic(
        TrafficSignals(**kw), min_impressions=MIN_IMPRESSIONS, floor=TRAFFIC
    )


def _conv(**kw):
    return assess_conversion(ConversionSignals(**kw), floor=CONVERSION)


def _dist(top_3=0, top_10=0, top_20=0, beyond_20=0, not_ranking=0):
    return {
        "top_3": top_3, "top_10": top_10, "top_20": top_20,
        "beyond_20": beyond_20, "not_ranking": not_ranking,
    }


# ── Visibility ──


def test_a_site_ranking_on_page_one_clears_the_bar():
    found = _vis(keyword_distribution=_dist(top_3=10, top_10=10, beyond_20=30))
    assert found.measurable
    assert found.ratio == pytest.approx(0.4)
    assert not found.below_floor


def test_a_relaunched_site_that_lost_its_rankings_is_below_it():
    """SMA, in October. Terms still tracked, almost none on page one."""
    found = _vis(keyword_distribution=_dist(top_3=1, top_10=3, not_ranking=96))
    assert found.ratio == pytest.approx(0.04)
    assert found.below_floor
    assert "4 of 100 tracked terms are in the top ten" in found.reason


def test_the_worse_of_rankings_and_citations_wins():
    """A site ranking well that no answer engine will quote still has a
    visibility problem, and so does the reverse."""
    found = _vis(
        keyword_distribution=_dist(top_3=50, top_10=30, beyond_20=20),
        ai_link_presence_pct=2.0,
        tracked_prompts=40,
    )
    assert found.below_floor
    assert "cite the brand" in found.reason
    # The reading that did not win still reaches the evidence.
    assert found.evidence["top_10_share"] == pytest.approx(0.8)


def test_citations_are_judged_against_their_own_bar_not_the_keyword_one():
    """25% citation is the bar, so 30% passes — even though 0.30 would be a
    failing top-ten share against a 0.30 floor only by a hair."""
    found = _vis(ai_link_presence_pct=30.0, tracked_prompts=40)
    assert not found.below_floor
    assert found.floor == pytest.approx(AI_PCT / 100)


def test_nothing_tracked_is_not_measurable():
    """Different from ranking badly. A client with no tracked terms has no
    visibility reading, and reporting zero would call that a catastrophe."""
    found = _vis()
    assert not found.measurable
    assert found.ratio is None


def test_prompts_without_a_count_are_ignored():
    found = _vis(ai_link_presence_pct=0.0, tracked_prompts=0)
    assert not found.measurable


# ── Traffic ──


def test_clicks_are_judged_against_what_the_rankings_should_earn():
    """Raw clicks cannot compare a site ranking third with one ranking tenth."""
    found = _traf(clicks=300, expected_clicks=1000, impressions=20000)
    assert found.ratio == pytest.approx(0.3)
    assert found.below_floor


def test_earning_most_of_what_the_curve_predicts_passes():
    found = _traf(clicks=700, expected_clicks=1000, impressions=20000)
    assert not found.below_floor


def test_no_search_console_is_not_measurable():
    assert not _traf().measurable


def test_a_thin_sample_is_not_measurable():
    """Eighteen of twenty-four clients have no Search Console at all; the rest
    need enough of it to mean something."""
    found = _traf(clicks=1, expected_clicks=10, impressions=MIN_IMPRESSIONS - 1)
    assert not found.measurable


def test_rankings_too_low_for_the_curve_decline_rather_than_divide_by_zero():
    """A visibility problem described in traffic's language. Returning a ratio
    of infinity — or of 1.0 — would both be lies."""
    found = _traf(clicks=0, expected_clicks=0, impressions=20000)
    assert not found.measurable
    assert "too low" in found.reason


# ── Conversion ──


def test_leads_are_judged_against_the_period_goal():
    found = _conv(leads=4, period_goal=10, lead_events_configured=True)
    assert found.ratio == pytest.approx(0.4)
    assert found.below_floor


def test_no_lead_events_configured_is_not_measurable():
    """Twenty of twenty-four clients. Nothing to measure against is not the
    same as failing to convert."""
    found = _conv(leads=0, period_goal=10, lead_events_configured=False)
    assert not found.measurable
    assert "no lead events configured" in found.reason


def test_no_goal_is_not_measurable():
    assert not _conv(leads=5, period_goal=None, lead_events_configured=True).measurable


# ── The ladder ──


def test_a_broken_upstream_rung_takes_the_month():
    """Visibility is worse against its own bar than conversion is against its
    own, and upstream wins anyway: a conversion fix on a page nobody can find
    is an hour at the wrong end of the funnel."""
    chosen = select_constraint([
        _vis(keyword_distribution=_dist(top_3=1, not_ranking=99)),
        _traf(clicks=700, expected_clicks=1000, impressions=20000),
        _conv(leads=1, period_goal=10, lead_events_configured=True),
    ])
    assert chosen is not None
    assert chosen.layer is Layer.VISIBILITY
    assert not chosen.by_comparison


def test_a_healthy_upstream_hands_the_month_down():
    chosen = select_constraint([
        _vis(keyword_distribution=_dist(top_3=50, top_10=30, beyond_20=20)),
        _traf(clicks=900, expected_clicks=1000, impressions=20000),
        _conv(leads=2, period_goal=10, lead_events_configured=True),
    ])
    assert chosen is not None and chosen.layer is Layer.CONVERSION


def test_an_unmeasurable_rung_is_stepped_over_not_treated_as_broken():
    """Most clients have no Search Console. Traffic must not win the month by
    being absent."""
    chosen = select_constraint([
        _vis(keyword_distribution=_dist(top_3=50, top_10=30, beyond_20=20)),
        _traf(),
        _conv(leads=1, period_goal=10, lead_events_configured=True),
    ])
    assert chosen is not None and chosen.layer is Layer.CONVERSION


def test_with_nothing_broken_the_softest_spot_wins_and_says_so():
    chosen = select_constraint([
        _vis(keyword_distribution=_dist(top_3=35, beyond_20=65)),
        _traf(clicks=650, expected_clicks=1000, impressions=20000),
        _conv(leads=9, period_goal=10, lead_events_configured=True),
    ])
    assert chosen is not None
    assert chosen.by_comparison, "nothing was below its floor"
    # Traffic has the least headroom: 0.65/0.60 = 1.08 against
    # visibility 0.35/0.30 = 1.17 and conversion 0.90/0.80 = 1.13.
    assert chosen.layer is Layer.TRAFFIC


def test_the_comparison_is_on_headroom_not_on_the_raw_ratio():
    """A raw ratio means something different on each rung. Visibility 0.35
    clears a 0.30 bar; conversion 0.50 misses a 0.80 one, and is the softer
    spot despite the larger number."""
    chosen = select_constraint([
        _vis(keyword_distribution=_dist(top_3=35, beyond_20=65)),
        _conv(leads=5, period_goal=10, lead_events_configured=True),
    ])
    assert chosen is not None and chosen.layer is Layer.CONVERSION


def test_only_one_measurable_rung_wins_by_default():
    """Seventeen clients can only be read on visibility."""
    chosen = select_constraint([
        _vis(keyword_distribution=_dist(top_3=50, top_10=30, beyond_20=20)),
        _traf(),
        _conv(lead_events_configured=False),
    ])
    assert chosen is not None and chosen.layer is Layer.VISIBILITY


def test_nothing_measurable_is_no_constraint_rather_than_a_guess():
    assert select_constraint([_vis(), _traf(), _conv()]) is None


def test_every_assessment_rides_along_whichever_wins():
    """The reader needs the other two to argue with the choice."""
    chosen = select_constraint([
        _vis(keyword_distribution=_dist(top_3=1, not_ranking=99)),
        _traf(clicks=700, expected_clicks=1000, impressions=20000),
        _conv(leads=1, period_goal=10, lead_events_configured=True),
    ])
    assert chosen is not None
    assert len(chosen.assessments) == 3
    assert chosen.of(Layer.TRAFFIC).ratio == pytest.approx(0.7)


# ── Through the engine, not just the functions ──


def test_diagnose_reads_every_rung_including_the_ai_one(db, client_a):
    """The AI branch referenced a model the module had not imported, and the
    whole suite stayed green because nothing drove `diagnose` with tracker
    stats in the window. Lint caught it; this would have."""
    from datetime import date as date_cls, timedelta
    from decimal import Decimal
    from uuid import uuid4

    from app.models.seranking import FactSerAiTrackerStats, FactSerKeyword
    from app.services.lever_engine import diagnose
    from tests.conftest import seed_required_sources

    end = date_cls.today()
    start = end - timedelta(days=29)

    db.add(
        FactSerKeyword(
            id=uuid4(),
            client_id=client_a.id,
            site_engine_id="1",
            keyword_id="k1",
            keyword="slab leak detection",
            current_position=42,
            checked_at=end,
        )
    )
    db.add(
        FactSerAiTrackerStats(
            id=uuid4(),
            client_id=client_a.id,
            metric_date=end,
            prompts_count=20,
            link_presence_pct=Decimal("5"),
        )
    )
    db.commit()
    seed_required_sources(db, client_a.id, end)
    # `seed_required_sources` watermarks se_ranking_ai but not
    # se_ranking_search, and the keyword window is gated on the latter.
    _watermark_search(db, client_a.id, end)

    result = diagnose(db, client_a, from_date=start, to_date=end)

    assert result.constraint is not None, "a client with tracked terms has a constraint"
    assert result.constraint.layer is Layer.VISIBILITY
    # Both readings were taken, not just the one that won.
    evidence = result.constraint.of(Layer.VISIBILITY).evidence
    assert evidence["tracked_keywords"] == 1
    assert evidence["ai_link_presence_pct"] == 5.0


def test_the_constraint_reaches_the_response(db, client_a):
    """`serialize_diagnose` names every field by hand and has silently dropped
    four before."""
    from datetime import date as date_cls, timedelta
    from uuid import uuid4

    from app.models.seranking import FactSerKeyword
    from app.services.decision_serialization import serialize_diagnose
    from app.services.lever_engine import diagnose
    from tests.conftest import seed_required_sources

    end = date_cls.today()
    db.add(
        FactSerKeyword(
            id=uuid4(),
            client_id=client_a.id,
            site_engine_id="1",
            keyword_id="k1",
            keyword="slab leak detection",
            current_position=55,
            checked_at=end,
        )
    )
    db.commit()
    seed_required_sources(db, client_a.id, end)
    _watermark_search(db, client_a.id, end)

    served = serialize_diagnose(
        diagnose(db, client_a, from_date=end - timedelta(days=29), to_date=end)
    )
    assert served.constraint is not None
    assert served.constraint.layer == "visibility"
    assert len(served.constraint.assessments) == 3


def _watermark_search(db, client_id, through) -> None:
    """The SE Ranking search watermark, which `seed_required_sources` omits."""
    import uuid as _uuid

    from app.models.job import DataWatermark, ValidationStatus

    db.add(
        DataWatermark(
            id=_uuid.uuid4(),
            client_id=client_id,
            source="se_ranking_search",
            fact_through_date=through,
            validation_status=ValidationStatus.PASSED,
        )
    )
    db.commit()


# ── Ordering and counts ──


def test_the_constraints_actions_come_first_without_dropping_the_rest():
    """The constraint ranks; it does not exclude. A conversion fix worth two
    leads stays on the page when visibility wins the month — it is simply not
    the first thing offered."""
    from app.models.decision import DiagnosticLayer, GrowthAction
    from app.services.decision_types import LeverFinding
    from app.services.lever_engine import (
        action_counts_by_layer,
        order_by_constraint,
    )
    from app.decisions.constraint import Constraint

    def _finding(layer: DiagnosticLayer, lever: str, name: str) -> LeverFinding:
        return LeverFinding(
            rule_key=name,
            lever=lever,
            stage=layer,
            diagnosis=name,
            recommended_action="a",
            success_metric="m",
            evidence_json={},
            baseline_metrics_json={},
            impact=0.0, confidence=0.0, urgency=0.0, effort=0.0, priority_score=0.0,
        )

    conversion = _finding(DiagnosticLayer.CONVERSION, GrowthAction.CONVERSION_PATH.value, "cta")
    traffic = _finding(DiagnosticLayer.TRAFFIC, GrowthAction.SERP_CTR.value, "title")
    visibility = _finding(DiagnosticLayer.VISIBILITY, GrowthAction.AI_VISIBILITY.value, "prompt")

    chosen = Constraint(layer=Layer.VISIBILITY, reason="r", assessments=())
    ordered = order_by_constraint([conversion, traffic, visibility], chosen)

    # Constraint first, then the remaining rungs in ladder order — traffic
    # before conversion, because that is the order they depend on each other.
    assert [f.rule_key for f in ordered] == ["prompt", "title", "cta"]
    assert len(ordered) == 3, "nothing is dropped"
    assert action_counts_by_layer(ordered) == {
        "visibility": 1, "traffic": 1, "conversion": 1
    }


def test_without_a_constraint_the_order_is_left_alone():
    from app.services.lever_engine import order_by_constraint

    assert order_by_constraint([], None) == []
