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
