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
        crawl_readable=True,
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


# ── What running it against real data found ─────────────────────────────────


def test_t1_refuses_a_query_that_names_the_site():
    """Boys Electrical, verbatim.

    /about-us sat at position 1.9 on 3,872 impressions with 4 clicks — 418
    "missed" against the curve, and the top three Traffic actions for that
    client. The query was "boyselectrical.com leadership team": the clicks
    went to the homepage at position 1. The shortfall is real and the snippet
    is not the cause.
    """
    page = traffic(
        impressions=3872.0,
        clicks=4.0,
        position=1.9,
        expected_clicks=422.0,
        top_query="boyselectrical.com leadership team",
        top_query_is_navigational=True,
    )
    assert _t(page) is None
    # The same page on a topic query is still a real finding.
    assert _t(traffic(**{**page.__dict__, "top_query_is_navigational": False})).action_id == "T-1"


def test_an_unknown_existing_offer_is_not_assumed_wrong():
    assert _l(lead(linked_offer_stages=frozenset({"generic"}))) is None


def test_brand_terms_cover_the_domain_and_the_name():
    from app.models.client import Client
    from app.services.page_signals import brand_terms, is_navigational

    client = Client(client_name="Boys Electrical Contractors", domain="www.boyselectrical.com")
    terms = brand_terms(client)
    assert "boyselectrical.com" in terms
    assert "boyselectrical" in terms

    assert is_navigational("boyselectrical.com leadership team", terms)
    assert is_navigational("boys electrical contractors reviews", terms)
    # The topic the client actually wants to win is not navigation.
    assert not is_navigational("emergency electrician nashville", terms)


def test_ga4s_unresolved_landing_page_is_not_a_candidate():
    """GA4 reports a landing page it could not resolve as "(not set)".

    It arrives with real sessions attached, reached the candidate list, and
    drew a T-3 telling somebody to rewrite the opening of "(not set)".
    """
    from app.services.page_signals import is_addressable

    assert not is_addressable("(not set)")
    assert not is_addressable("")
    assert not is_addressable(None)
    assert is_addressable("https://example.com/a")
    assert is_addressable("/a")


def test_a_conversion_page_is_not_told_to_route_onward():
    """SMA's declared conversion page is its homepage.

    So the highest-scoring lead action told the homepage to add an in-content
    link to the homepage.
    """
    page = lead(url="/", is_conversion_page=True, matched_offers=())
    assert _l(page) is None

    # And it is never offered as its own destination.
    routed = lead(url="/", is_conversion_page=True, matched_offers=("/contact",))
    assert _l(routed) is None


@pytest.mark.parametrize('sessions', [0, 1, 49])
def test_lead_actions_do_not_spend_work_on_tiny_traffic(sessions):
    from app.decisions.catalog import l1_route_to_the_next_step, l2_add_a_call_to_action, l3_match_the_offer_to_the_reader
    page = lead(sessions=sessions, conversion_elements=0, linked_offer_stages=frozenset({'bofu'}))
    for rule in (l1_route_to_the_next_step, l2_add_a_call_to_action, l3_match_the_offer_to_the_reader):
        assert rule(page) is None


def test_lead_actions_require_a_readable_crawl_and_exclude_utility_pages():
    assert _l(lead(crawl_readable=False, conversion_elements=0)) is None
    assert _l(lead(url='https://example.com/privacy-policy/', conversion_elements=0)) is None
    assert _l(lead(sessions=50)).action_id == 'L-1'


def test_unknown_destination_intent_does_not_justify_a_replacement():
    assert _l(lead(linked_offer_stages=frozenset({'generic'}))) is None
    assert _l(lead(stage='tofu', matched_offers=(), conversion_elements=0)) is None


def test_loader_requires_declared_offer_intent_and_first_party_crawl(db, client_a):
    from datetime import date, datetime, timezone
    from app.models.config import ClientConversionPage, ClientPageStage, OrganicChannel
    from app.models.ga4 import FactGa4Traffic
    from app.models.crawl import FactCrawlPageSnapshot, CRAWL_SOURCE_FIRST_PARTY, CRAWL_SOURCE_SE_RANKING
    from app.services.page_signals import load_page_candidates
    today=date(2026,9,30); url='https://example.com/guide'; offer='https://example.com/contact'
    db.add(FactGa4Traffic(client_id=client_a.id,date=today,raw_url=url,normalized_url=url,channel=OrganicChannel.ORGANIC_SEARCH,sessions=200))
    db.add(ClientPageStage(client_id=client_a.id,normalized_url=url,stage='tofu',confirmed_at=datetime.now(timezone.utc)))
    destination=ClientConversionPage(client_id=client_a.id,normalized_url=offer,label='Contact',stage=None)
    db.add(destination)
    for source in (CRAWL_SOURCE_FIRST_PARTY, CRAWL_SOURCE_SE_RANKING):
        db.add(FactCrawlPageSnapshot(client_id=client_a.id,source=source,snapshot_date=today,raw_url=url,normalized_url=url,status_code=200,sections=[],conversion_elements=0))
    db.commit()
    page=next(p for p in load_page_candidates(db,client_a,today=today) if p.url==url)
    assert page.crawl_readable and page.matched_offers==() and _l(page) is None
    destination.stage='mofu';db.flush()
    page=next(p for p in load_page_candidates(db,client_a,today=today) if p.url==url)
    assert page.matched_offers==(offer,) and _l(page).action_id=='L-1'


def test_low_engagement_on_a_small_sample_does_not_prescribe_a_rewrite():
    from app.decisions.catalog import t3_realign_to_the_audience
    page=traffic(sessions=73,engaged_sessions=19,site_median_engagement=0.45)
    assert t3_realign_to_the_audience(page) is None
    found=t3_realign_to_the_audience(traffic(sessions=300,engaged_sessions=90,site_median_engagement=0.6))
    assert found.metric_key=='decision'
    assert 'tracking' in found.done_when and 'only if' in found.done_when
