"""Tests for page eligibility classification."""

from app.services.page_eligibility import PageType, classify_page_url


def test_opt_out_preferences_excluded():
    classification = classify_page_url("https://smamarketing.net/opt-out-preferences")
    assert classification.eligible_for_growth_action is False
    assert classification.page_type == PageType.UTILITY
    assert classification.excluded_reason == "opt_out_preferences"


def test_pagination_excluded():
    classification = classify_page_url("https://example.com/blog/page/2")
    assert classification.eligible_for_growth_action is False
    assert classification.excluded_reason == "pagination"


def test_commercial_service_page_eligible():
    classification = classify_page_url("https://smamarketing.net/services/sem")
    assert classification.eligible_for_growth_action is True
    assert classification.page_type == PageType.COMMERCIAL
    assert classification.commercial_priority == 5


def test_a_flat_blog_post_has_no_topic():
    """Its slug is not a subject it shares with anything.

    This returned the slug anyway, so every post got a topic of its own and two
    things quietly did nothing: findings grouped by topic grouped one page each,
    and topic lead rates averaged a single page.
    """
    result = classify_page_url("https://smamarketing.com/blog/schema-markup-guide")

    assert result.page_type == PageType.INFORMATIONAL
    assert result.priority_topic is None


def test_a_categorised_post_takes_its_category():
    result = classify_page_url("https://example.com/blog/local-seo/checklist-for-dentists")

    assert result.priority_topic == "local seo"


def test_the_category_index_itself_is_not_a_topic():
    """One segment is ambiguous: category index or post, no way to tell."""
    assert classify_page_url("https://example.com/blog/local-seo").priority_topic is None


def test_a_deeper_path_still_takes_the_first_segment():
    result = classify_page_url("https://example.com/blog/roofing/metal/standing-seam")

    assert result.priority_topic == "roofing"
