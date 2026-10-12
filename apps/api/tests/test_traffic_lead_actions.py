"""The Traffic and Leads actions.

Until these existed the catalog held only Visibility actions, so a client the
engine put on Traffic got a plan made of Visibility spillover, or an empty
one: the run named the problem and prescribed for a different branch.

What each test pins is a refusal. Every one of these actions can be wrong in
the same way — firing on a page where the number it cites does not mean what
the sentence claims — so most of this file is about when they stay silent.
"""

from __future__ import annotations

import pytest

from app.decisions.catalog import (
    LEAD_ACTIONS,
    TRAFFIC_ACTIONS,
    prescribe_page,
)
from app.decisions.page_targets import (
    PageCandidate,
    rank_for_leads,
    rank_for_traffic,
)
from app.decisions.triage import Branch


def traffic(**kw) -> PageCandidate:
    base = dict(
        url="/a",
        impressions=1000.0,
        clicks=50.0,
        position=2.0,
        expected_clicks=120.0,
        top_query="seo agency",
    )
    base.update(kw)
    return PageCandidate(**base)


def lead(**kw) -> PageCandidate:
    base = dict(
        url="/guide",
        sessions=200.0,
        stage="tofu",
        matched_offers=("/newsletter",),
        conversion_elements=2,
    )
    base.update(kw)
    return PageCandidate(**base)


def _t(page: PageCandidate):
    return prescribe_page(page, actions=TRAFFIC_ACTIONS)


def _l(page: PageCandidate):
    return prescribe_page(page, actions=LEAD_ACTIONS)


# ── T-1 ─────────────────────────────────────────────────────────────────────


def test_t1_fires_on_a_top_three_page_under_the_curve():
    found = _t(traffic())
    assert found is not None
    assert found.action_id == "T-1"
    assert found.branch is Branch.TRAFFIC
    assert found.score == pytest.approx(70.0)
    # The sentence has to carry the numbers it is arguing from.
    assert "position 2.0" in found.why
    assert "120" in found.why


def test_t1_stays_quiet_below_the_top_three():
    # At position 8 a CTR under the curve is mostly explained by rank, so a
    # title rewrite would be sold on a number it cannot move.
    assert _t(traffic(position=8.0, expected_clicks=30.0)) is None


def test_t1_stays_quiet_on_too_few_impressions():
    # A handful of searches: the curve is noise at that size.
    assert _t(traffic(impressions=40.0, clicks=1.0, expected_clicks=5.0)) is None


def test_t1_stays_quiet_when_the_page_beats_the_curve():
    assert _t(traffic(clicks=200.0)) is None


def test_t1_needs_a_position_to_compare_against():
    assert _t(traffic(position=None, expected_clicks=None)) is None


# ── T-3 ─────────────────────────────────────────────────────────────────────


def test_t3_fires_on_engagement_under_the_site_median():
    page = traffic(
        position=9.0,
        expected_clicks=10.0,
        clicks=10.0,
        sessions=300.0,
        engaged_sessions=90.0,
        site_median_engagement=0.6,
    )
    found = _t(page)
    assert found is not None
    assert found.action_id == "T-3"
    assert "30%" in found.why and "60%" in found.why


def test_t3_compares_against_the_site_not_a_number_somebody_picked():
    # The same 30% engagement passes on a site whose median is lower.
    page = traffic(
        position=9.0,
        expected_clicks=10.0,
        clicks=10.0,
        sessions=300.0,
        engaged_sessions=90.0,
        site_median_engagement=0.25,
    )
    assert _t(page) is None


def test_t3_needs_enough_sessions_to_judge():
    page = traffic(
        position=9.0,
        expected_clicks=10.0,
        clicks=10.0,
        sessions=10.0,
        engaged_sessions=1.0,
        site_median_engagement=0.6,
    )
    assert _t(page) is None


def test_t3_stays_quiet_where_ga4_never_sent_engagement():
    page = traffic(
        position=9.0,
        expected_clicks=10.0,
        clicks=10.0,
        sessions=300.0,
        engaged_sessions=None,
        site_median_engagement=0.6,
    )
    assert _t(page) is None


# ── Leads ───────────────────────────────────────────────────────────────────


def test_no_lead_action_fires_without_a_confirmed_stage():
    # A lead action on a stage guessed from the URL is the mistake declared
    # conversion pages were built to stop.
    assert _l(lead(stage=None, conversion_elements=0)) is None


def test_l1_fires_on_a_page_with_no_in_content_route_out():
    found = _l(lead())
    assert found is not None
    assert found.action_id == "L-1"
    assert "/newsletter" in found.done_when
    assert found.check_after_days == 30


def test_l1_does_not_fire_on_a_page_that_already_routes_onward():
    found = _l(lead(linked_offer_stages=frozenset({"mofu"})))
    assert found is None or found.action_id != "L-1"


def test_l1_does_not_fire_on_the_bottom_of_the_funnel():
    # A page for somebody ready to buy is the next step.
    assert _l(lead(stage="bofu", matched_offers=("/quote",))) is None


def test_l1_stays_quiet_when_there_is_nowhere_to_send_them():
    assert _l(lead(matched_offers=())) is None


def test_l2_fires_when_the_page_never_asks():
    page = lead(linked_offer_stages=frozenset({"mofu"}), conversion_elements=0)
    found = _l(page)
    assert found is not None
    assert found.action_id == "L-2"
    # The crawl counts these and does not say where they sit, so the flag
    # says what the action cannot claim.
    assert "cta_position_unknown" in found.flags


def test_l2_stays_quiet_where_the_crawl_never_counted():
    page = lead(linked_offer_stages=frozenset({"mofu"}), conversion_elements=None)
    assert _l(page) is None


def test_l3_fires_when_every_route_out_is_wrong_for_the_reader():
    # Still learning, and the only way onward is a quote form.
    page = lead(linked_offer_stages=frozenset({"bofu"}))
    found = _l(page)
    assert found is not None
    assert found.action_id == "L-3"
    assert "still learning" in found.why
    assert found.check_after_days == 45


def test_l3_stays_quiet_when_one_route_already_suits():
    page = lead(linked_offer_stages=frozenset({"bofu", "mofu"}))
    assert _l(page) is None


# ── Ranking ─────────────────────────────────────────────────────────────────


def test_traffic_ranks_on_clicks_actually_missed():
    small = traffic(url="/small", impressions=200.0, clicks=5.0, expected_clicks=25.0)
    big = traffic(url="/big", impressions=5000.0, clicks=100.0, expected_clicks=600.0)
    assert [p.url for p in rank_for_traffic([small, big])] == ["/big", "/small"]


def test_leads_rank_on_the_sessions_being_spent():
    quiet = lead(url="/quiet", sessions=10.0)
    busy = lead(url="/busy", sessions=900.0)
    assert [p.url for p in rank_for_leads([quiet, busy])] == ["/busy", "/quiet"]


def test_a_page_with_no_sessions_is_not_a_lead_candidate():
    assert rank_for_leads([lead(sessions=0.0)]) == []
