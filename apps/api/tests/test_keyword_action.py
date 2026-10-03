"""Telling a client to build a page they already have.

"seo services", "seo agency" and "seo company" were the top three
recommendations on smamarketing.com, each saying "a term tracked for months
with no page behind it". All three are answered by /capabilities/seo.

Not ranking in the top hundred and having no page are different problems
with opposite fixes, and Search Console already reports which one it is.
"""

from __future__ import annotations

from app.services.lever_engine import ExistingPageForQuery, keyword_action

SEO_PAGE = ExistingPageForQuery(
    page_url="https://smamarketing.com/capabilities/seo",
    impressions=1_240,
    average_position=38.0,
)


def test_it_names_the_page_that_already_exists():
    action = keyword_action("keyword_not_ranking", "seo services", None, SEO_PAGE)
    assert "already exists" in action
    assert "https://smamarketing.com/capabilities/seo" in action
    assert "1,240 impressions" in action
    assert "position 38" in action


def test_it_does_not_tell_you_to_build_what_you_have():
    action = keyword_action("keyword_not_ranking", "seo services", None, SEO_PAGE)
    assert "build a page" not in action.lower()
    assert "drop it from the watchlist" not in action


def test_it_warns_against_a_second_page_on_the_same_term():
    action = keyword_action("keyword_not_ranking", "seo services", None, SEO_PAGE)
    assert "splits" in action


def test_with_no_page_it_still_says_to_build_one():
    """The original advice was not wrong, only unverified."""
    action = keyword_action("keyword_not_ranking", "quantum plumbing", None, None)
    assert "Build one" in action
    assert "drop it from the watchlist" in action


def test_the_no_page_claim_is_now_about_impressions_not_assumption():
    action = keyword_action("keyword_not_ranking", "quantum plumbing", None, None)
    assert "no page draws an impression for it" in action


def test_a_keyword_that_slipped_is_unaffected():
    action = keyword_action(
        "keyword_fell_top5", "local seo", "https://smamarketing.com/capabilities/local-seo"
    )
    assert "Recover" in action
    assert "capabilities/local-seo" in action
