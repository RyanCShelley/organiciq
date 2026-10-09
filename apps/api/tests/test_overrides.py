"""Saying "not this page" and "not this client".

Boys Electrical's traffic branch failed on a careers page: 52 sessions, no
conversions. Right, and useless — nobody is being paid to recruit
electricians this quarter — and there was no way to say so, so the engine
would have named it again every month.
"""

from __future__ import annotations

from app.decisions.overrides import Exclusion, filter_pages, is_excluded, matches

CAREERS = Exclusion("/careers*", "Not recruiting this quarter.")


def test_a_section_excludes_what_is_under_it():
    assert matches("https://x.com/careers", "/careers*")
    assert matches("https://x.com/careers/electrician", "/careers*")


def test_a_prefix_stops_at_a_path_boundary():
    """'/car*' must not take '/carbon-fiber' — the kind of quiet over-match
    nobody notices until a real page stops being reported."""
    assert not matches("https://x.com/carbon-fiber", "/car*")
    assert not matches("https://x.com/careers-advice", "/careers*")


def test_one_page_excludes_only_itself():
    assert matches("https://x.com/careers", "/careers")
    assert not matches("https://x.com/careers/role", "/careers")


def test_a_trailing_slash_is_not_a_different_page():
    assert matches("https://x.com/careers/", "/careers")
    assert matches("https://x.com/careers", "/careers/")


def test_the_reason_comes_back_with_the_match():
    """A decision taken in March has to be legible in September."""
    found = is_excluded("https://x.com/careers/electrician", [CAREERS])
    assert found is not None
    assert found.reason == "Not recruiting this quarter."


def test_everything_else_is_untouched():
    pages = [
        "https://x.com/",
        "https://x.com/careers",
        "https://x.com/services/panel-upgrades",
    ]
    assert filter_pages(pages, [CAREERS]) == [
        "https://x.com/",
        "https://x.com/services/panel-upgrades",
    ]


def test_no_exclusions_excludes_nothing():
    assert filter_pages(["https://x.com/careers"], []) == ["https://x.com/careers"]
