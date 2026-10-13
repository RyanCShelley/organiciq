"""What to do about a page that is losing ground.

One rule runs through all of these: nothing fires on impressions alone.
A page can shed demand because the SERP changed shape around it, and
prescribing a refresh for a page that is climbing spends a month of a
client's allowance on something that is already working.
"""

from __future__ import annotations

from datetime import date

from app.decisions.catalog import prescribe_page
from app.decisions.page_targets import PageCandidate
from app.decisions.update_catalog import (
    MIN_PRIOR_IMPRESSIONS,
    UPDATE_ACTIONS,
    rank_for_updates,
    u1_refresh_the_page,
    u2_win_back_the_position,
    u3_answer_the_question_it_draws,
    u6_fix_the_markup,
)


def _decaying(**overrides) -> PageCandidate:
    """A page that has plainly lost ground, for the triggers to narrow."""
    fields = {
        "url": "https://example.com/guide",
        "impressions": 300.0,
        "prior_impressions": 1200.0,
        "position": 14.0,
        "prior_position": 9.0,
        "word_count": 1500,
    }
    fields.update(overrides)
    return PageCandidate(**fields)


# ── The guard every action shares ──


def test_a_page_whose_ranking_improved_gets_nothing():
    """ACCTek's /managed-it-services-syracuse-ny, from production.

    2,817 impressions gone while the position improved from 32.7 to 21.5.
    The SERP changed shape; the page did not decay.
    """
    page = _decaying(
        impressions=4707.0, prior_impressions=7524.0, position=21.5, prior_position=32.7
    )
    assert prescribe_page(page, actions=UPDATE_ACTIONS) is None


def test_a_small_page_is_not_judged_on_a_small_fall():
    """Below the floor, halving is four impressions."""
    page = _decaying(impressions=20.0, prior_impressions=MIN_PRIOR_IMPRESSIONS - 1)
    assert u1_refresh_the_page(page) is None


def test_a_page_with_no_earlier_figures_is_not_decaying():
    assert u1_refresh_the_page(_decaying(prior_impressions=0.0)) is None


def test_a_page_that_barely_moved_is_left_alone():
    page = _decaying(impressions=1100.0, prior_impressions=1200.0)
    assert u1_refresh_the_page(page) is None


# ── U-1 ──


def test_u1_fires_on_a_plain_decline():
    found = u1_refresh_the_page(_decaying())
    assert found is not None
    assert found.action_id == "U-1"
    assert found.metric_key == "page_impressions"
    assert "75%" in found.why
    assert found.score == 900.0


def test_u1_will_not_tell_anyone_to_refresh_a_stub():
    """Whatever is wrong with a 90-word page, updating it is not it."""
    assert u1_refresh_the_page(_decaying(word_count=90)) is None


def test_u1_says_how_old_the_page_is_when_it_knows():
    found = u1_refresh_the_page(_decaying(content_updated_on=date(2020, 1, 1)))
    assert "years ago" in found.why


def test_u1_says_nothing_about_age_when_no_source_carried_a_date():
    """"Last updated unknown" is noise. Silence is honest."""
    found = u1_refresh_the_page(_decaying(content_updated_on=None))
    assert "updated" not in found.why


# ── U-2 ──


def test_u2_fires_when_a_top_three_term_slipped():
    found = u2_win_back_the_position(
        _decaying(
            top_lost_query="seo audit",
            top_lost_query_prior_position=2.0,
            top_lost_query_position=9.0,
        )
    )
    assert found is not None
    assert found.action_id == "U-2"
    assert found.term == "seo audit"
    assert found.metric_key == "term_position"


def test_u2_ignores_a_term_that_was_never_near_the_top():
    assert (
        u2_win_back_the_position(
            _decaying(
                top_lost_query="seo audit",
                top_lost_query_prior_position=18.0,
                top_lost_query_position=31.0,
            )
        )
        is None
    )


def test_u2_ignores_a_term_that_is_still_up_there():
    assert (
        u2_win_back_the_position(
            _decaying(
                top_lost_query="seo audit",
                top_lost_query_prior_position=2.0,
                top_lost_query_position=2.4,
            )
        )
        is None
    )


def test_u2_says_nothing_about_a_term_that_vanished():
    """Gone from the results is a different problem, and "win it back" is
    the wrong instruction for it."""
    assert (
        u2_win_back_the_position(
            _decaying(
                top_lost_query="seo audit",
                top_lost_query_prior_position=2.0,
                top_lost_query_position=None,
            )
        )
        is None
    )


def test_u2_beats_u1_because_its_brief_is_sharper():
    page = _decaying(
        top_lost_query="seo audit",
        top_lost_query_prior_position=2.0,
        top_lost_query_position=9.0,
    )
    assert prescribe_page(page, actions=UPDATE_ACTIONS).action_id == "U-2"


# ── U-3 ──


def test_u3_fires_when_no_heading_asks_what_people_ask():
    found = u3_answer_the_question_it_draws(
        _decaying(
            top_lost_query="how to track ai overviews",
            sections=({"heading": "Why visibility matters", "level": 2},),
        )
    )
    assert found is not None
    assert found.action_id == "U-3"


def test_u3_is_satisfied_by_a_heading_that_already_asks_it():
    """Matched on content words: "how to track ai overviews" and "How do I
    track AI Overviews?" are one question, and a string compare says not."""
    assert (
        u3_answer_the_question_it_draws(
            _decaying(
                top_lost_query="how to track ai overviews",
                sections=({"heading": "How do I track AI Overviews?", "level": 2},),
            )
        )
        is None
    )


def test_u3_is_satisfied_by_an_faq_entry():
    assert (
        u3_answer_the_question_it_draws(
            _decaying(
                top_lost_query="how to track ai overviews",
                sections=({"heading": "Something else", "level": 2},),
                faq_questions=("How to track AI Overviews",),
            )
        )
        is None
    )


def test_u3_stays_quiet_when_the_crawl_captured_no_headings():
    """Null sections is "the crawl predates the capture", not "no headings"."""
    assert (
        u3_answer_the_question_it_draws(
            _decaying(top_lost_query="how to track ai overviews", sections=())
        )
        is None
    )


def test_u3_ignores_a_term_that_is_not_a_question():
    assert (
        u3_answer_the_question_it_draws(
            _decaying(
                top_lost_query="seo agency charleston",
                sections=({"heading": "Our work", "level": 2},),
            )
        )
        is None
    )


# ── U-6 ──


def test_u6_fires_on_markup_that_does_not_parse():
    found = u6_fix_the_markup(
        PageCandidate(
            url="https://example.com/a",
            impressions=800.0,
            broken_schema=("Article",),
        )
    )
    assert found is not None
    assert found.action_id == "U-6"
    assert "Article" in found.why


def test_u6_needs_the_page_to_be_worth_the_time():
    assert (
        u6_fix_the_markup(
            PageCandidate(
                url="https://example.com/a", impressions=3.0, broken_schema=("Article",)
            )
        )
        is None
    )


def test_u6_does_not_fire_on_a_page_with_no_markup_at_all():
    """Absent is V-5 and V-7's business. This one is about broken."""
    assert (
        u6_fix_the_markup(PageCandidate(url="https://example.com/a", impressions=800.0))
        is None
    )


# ── The order ──


def test_the_biggest_loss_sorts_first():
    small = _decaying(url="https://example.com/small", impressions=10.0, prior_impressions=200.0)
    big = _decaying(url="https://example.com/big", impressions=100.0, prior_impressions=5000.0)
    assert [p.url for p in rank_for_updates([small, big])][0] == big.url


def test_a_page_that_lost_nothing_is_not_in_the_queue():
    steady = PageCandidate(url="https://example.com/fine", impressions=900.0, prior_impressions=800.0)
    assert rank_for_updates([steady]) == []


# ── What the first dry run against production found ──


def test_u2_refuses_a_query_that_names_the_site():
    """Boys Electrical's /commercial, from the first real dry run.

    It was prescribed "win back the position" for "boyselectrical.com
    leadership team". A brand query is answered by whichever of your own
    pages sits top, and no rewrite moves it — the same trap T-1 fell into
    on the same site.
    """
    page = _decaying(
        top_lost_query="boyselectrical.com leadership team",
        top_lost_query_is_navigational=True,
        top_lost_query_prior_position=2.9,
        top_lost_query_position=6.0,
    )
    assert u2_win_back_the_position(page) is None


def test_u2_ignores_an_average_breathing():
    """2.9 to 3.5 crosses the line and is not a position lost.

    An average position is a weighted mean over four weeks; half a place
    of movement is what it does when nothing happens.
    """
    page = _decaying(
        top_lost_query="commercial electrician",
        top_lost_query_prior_position=2.9,
        top_lost_query_position=3.5,
    )
    assert u2_win_back_the_position(page) is None


def test_u2_still_fires_on_a_real_fall():
    page = _decaying(
        top_lost_query="commercial electrician",
        top_lost_query_prior_position=2.0,
        top_lost_query_position=8.0,
    )
    assert u2_win_back_the_position(page).action_id == "U-2"


def test_a_brand_query_is_never_what_a_page_is_losing_most_on():
    """U-1 named it in the brief, which sends somebody to rewrite a page
    for a query the homepage was always going to answer."""
    found = u1_refresh_the_page(
        _decaying(
            top_lost_query="boyselectrical.com leadership team",
            top_lost_query_is_navigational=True,
        )
    )
    assert "boyselectrical.com" not in found.why
