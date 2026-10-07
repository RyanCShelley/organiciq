"""T1 — the page takes traffic and does not convert it.

The entry gate is relative on purpose. A fixed session floor was measured
first and would have emptied the trigger: SMA has six pages above thirty
sessions in a month and two above a hundred.
"""

from __future__ import annotations

import pytest

from app.decisions.triggers.coverage import SkipReason
from app.decisions.triggers.t1_conversion import (
    Offer,
    PageSignals,
    T1Inputs,
    baseline_bounce,
    classify_page,
    eligible_gate,
    pick_offer,
)

LIMITS: dict = {}


def _page(url: str, sessions: float, engaged: float, **kwargs) -> PageSignals:
    return PageSignals(
        url=url,
        sessions=sessions,
        engaged_sessions=engaged,
        page_stage=kwargs.pop("stage", "tofu"),
        in_content_links_to_offers=kwargs.pop("links", 2),
        in_crawl=kwargs.pop("in_crawl", True),
    )


# ── The gate ──


def test_a_six_page_site_admits_its_top_two():
    pages = [_page(f"https://x/{i}", 600 - i * 50, 300) for i in range(6)]
    gate = eligible_gate(pages, min_sessions=30, top_share=0.25)
    assert [p.url for p in gate] == ["https://x/0", "https://x/1"]


def test_a_site_with_three_eligible_pages_admits_one():
    """Never zero: the busiest page of three is still the busiest page."""
    pages = [_page(f"https://x/{i}", 100 - i, 50) for i in range(3)]
    assert len(eligible_gate(pages, min_sessions=30, top_share=0.25)) == 1


def test_the_floor_still_applies():
    pages = [_page("https://x/a", 29, 10), _page("https://x/b", 12, 4)]
    assert eligible_gate(pages, min_sessions=30, top_share=0.25) == []


def test_a_large_site_is_still_cut_to_the_share():
    pages = [_page(f"https://x/{i}", 1000 - i, 500) for i in range(100)]
    assert len(eligible_gate(pages, min_sessions=30, top_share=0.25)) == 25


# ── 1a ──


def test_the_baseline_excludes_the_page_being_tested():
    """On a six-page site a page can be a third of the bar it is measured
    against, which is how a bad page clears its own average."""
    pages = [_page("https://x/a", 600, 180), _page("https://x/b", 400, 320)]
    baseline, sessions = baseline_bounce(pages, exclude="https://x/a")
    assert sessions == 400
    assert baseline == pytest.approx(0.2)


def test_a_page_losing_visitors_faster_than_the_site_is_1a():
    pages = [
        _page("https://x/a", 600, 180),
        _page("https://x/b", 300, 240),
        _page("https://x/c", 150, 120),
    ]
    prescription, skip, rule = classify_page(
        pages[0], T1Inputs(pages=pages, has_crawl=True), thresholds=LIMITS
    )
    assert rule == "1a"
    assert skip is None
    assert prescription.cause == "conversion_proof_missing"
    assert "first 120 words" in prescription.steps[0].text
    assert prescription.evidence["baseline"] == "site_session_weighted_excluding_page"


def test_a_thin_baseline_skips_rather_than_guesses():
    """Below 200 baseline sessions the site average is not an average."""
    pages = [_page("https://x/a", 600, 60), _page("https://x/b", 80, 70)]
    _, skip, rule = classify_page(
        pages[0], T1Inputs(pages=pages, has_crawl=False), thresholds=LIMITS
    )
    assert rule is None
    assert skip is SkipReason.INSUFFICIENT_BASELINE


def test_bounce_exactly_at_the_multiple_does_not_fire():
    # Baseline 20%, multiple 1.2 -> the bar is 24%. A page at 24% is not over it.
    pages = [_page("https://x/a", 500, 380), _page("https://x/b", 400, 320)]
    _, _, rule = classify_page(
        pages[0], T1Inputs(pages=pages, has_crawl=True), thresholds=LIMITS
    )
    assert rule != "1a"


# ── 1b ──


def test_a_page_with_no_in_content_link_to_an_offer_is_1b():
    pages = [_page("https://x/a", 600, 480, links=0), _page("https://x/b", 400, 320)]
    prescription, _, rule = classify_page(
        pages[0],
        T1Inputs(
            pages=pages,
            offers=[Offer("https://x/contact", "Contact us", None)],
            has_crawl=True,
        ),
        thresholds=LIMITS,
    )
    assert rule == "1b"
    assert prescription.cause == "conversion_cta_missing"
    assert prescription.steps[0].target == "https://x/contact"
    assert "Navigation and footer links do not count" in prescription.steps[0].detail


def test_1a_beats_1b():
    """Losing them before the page speaks is the bigger problem."""
    pages = [_page("https://x/a", 600, 60, links=0), _page("https://x/b", 400, 320)]
    _, _, rule = classify_page(
        pages[0],
        T1Inputs(pages=pages, offers=[Offer("https://x/c", "C")], has_crawl=True),
        thresholds=LIMITS,
    )
    assert rule == "1a"


def test_no_crawl_skips_rather_than_claiming_there_is_no_link():
    pages = [_page("https://x/a", 600, 480, links=None), _page("https://x/b", 400, 320)]
    _, skip, rule = classify_page(
        pages[0], T1Inputs(pages=pages, has_crawl=False), thresholds=LIMITS
    )
    assert rule is None
    assert skip is SkipReason.CRAWL_NOT_READY


def test_a_page_the_crawl_never_reached_skips_too():
    pages = [
        _page("https://x/a", 600, 480, links=None, in_crawl=False),
        _page("https://x/b", 400, 320),
    ]
    _, skip, _ = classify_page(
        pages[0], T1Inputs(pages=pages, has_crawl=True), thresholds=LIMITS
    )
    assert skip is SkipReason.PAGE_NOT_CRAWLED


def test_with_no_declared_offer_it_asks_rather_than_inventing_one():
    pages = [_page("https://x/a", 600, 480, links=0), _page("https://x/b", 400, 320)]
    prescription, _, rule = classify_page(
        pages[0], T1Inputs(pages=pages, offers=[], has_crawl=True), thresholds=LIMITS
    )
    assert rule == "1b"
    assert prescription.cause == "conversion_offer_missing"
    assert prescription.steps[0].human is True


def test_the_offer_matching_the_page_stage_wins():
    offers = [
        Offer("https://x/demo", "Book a demo", "bofu"),
        Offer("https://x/guide", "Download the guide", "tofu"),
    ]
    assert pick_offer(offers, "tofu").url == "https://x/guide"
    assert pick_offer(offers, "bofu").url == "https://x/demo"
    assert pick_offer(offers, None).url == "https://x/demo"


# ── No fallback ──


def test_a_page_that_matches_nothing_emits_nothing():
    """A generic finding on a page we could not diagnose is the thing this
    rebuild exists to remove."""
    pages = [_page("https://x/a", 600, 480, links=3), _page("https://x/b", 400, 320)]
    prescription, skip, rule = classify_page(
        pages[0],
        T1Inputs(pages=pages, offers=[Offer("https://x/c", "C")], has_crawl=True),
        thresholds=LIMITS,
    )
    assert prescription is None
    assert rule is None
    assert skip is SkipReason.NO_RULE_MATCHED
