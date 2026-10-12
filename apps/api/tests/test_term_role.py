"""Primary earns the title; secondary earns a section.

`term_role` was imported from the keyword CSV, stored, served to the page,
and read by no decision anywhere — 203 of SMA's terms carried one and it
changed nothing. The spec always said what it was for: "a primary term earns
a title rewrite, a secondary term earns a section".
"""

from __future__ import annotations

import pytest

from app.decisions.catalog import (
    PageFacts,
    prescribe,
    v1_term_in_high_value_spots,
    v8_secondary_term_section,
)
from app.decisions.targets import Candidate, ScoredCandidate

TERM = "local seo company"


def _target(role: str | None) -> ScoredCandidate:
    return ScoredCandidate(
        candidate=Candidate(
            keyword=TERM,
            target_url="/capabilities/local-seo",
            ranking_url="/capabilities/local-seo",
            position=14.0,
            volume=2400.0,
            term_role=role,
        ),
        score=1.0,
        factors={},
    )


def _bare_page(**kw) -> PageFacts:
    base = dict(
        url="/capabilities/local-seo",
        title="Local SEO services",
        description="Local SEO services",
        headings=("Local SEO services", "Our approach"),
    )
    base.update(kw)
    return PageFacts(**base)


# ── Primary ─────────────────────────────────────────────────────────────────


def test_a_primary_term_earns_the_title():
    found = v1_term_in_high_value_spots(_target("primary"), _bare_page())
    assert found is not None
    assert found.action_id == "V-1"
    assert "title" in found.done_when


def test_a_term_with_no_role_is_treated_as_primary():
    # Every client mapped before roles existed has none, and a page whose
    # term is missing from its title is still the finding.
    assert v1_term_in_high_value_spots(_target(None), _bare_page()) is not None


# ── Secondary ───────────────────────────────────────────────────────────────


def test_a_secondary_term_is_never_told_to_take_the_title():
    """A page has one title and it belongs to the primary term.

    Asking for a secondary term in it is asking for the primary term out —
    and the engine would find that missing next month and ask for it back.
    """
    assert v1_term_in_high_value_spots(_target("secondary"), _bare_page()) is None


def test_a_secondary_term_earns_a_section():
    found = v8_secondary_term_section(_target("secondary"), _bare_page())
    assert found is not None
    assert found.action_id == "V-8"
    assert "H2" in found.done_when
    # And says outright what it is not asking for.
    assert "title and H1 are left alone" in found.done_when


def test_a_secondary_term_already_in_a_heading_is_left_alone():
    page = _bare_page(headings=("Local SEO services", f"Choosing a {TERM}"))
    assert v8_secondary_term_section(_target("secondary"), page) is None


def test_the_section_action_is_only_for_secondary_terms():
    for role in ("primary", None):
        assert v8_secondary_term_section(_target(role), _bare_page()) is None


# ── Together ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["primary", "secondary", None])
def test_exactly_one_of_the_two_fires(role: str | None):
    """They are alternatives, not a sequence: a term is either the page's
    primary or one of its secondaries."""
    found = [
        action(_target(role), _bare_page())
        for action in (v1_term_in_high_value_spots, v8_secondary_term_section)
    ]
    assert sum(1 for f in found if f is not None) == 1


def test_the_catalog_picks_the_right_one():
    assert prescribe(_target("primary"), _bare_page()).action_id == "V-1"
    assert prescribe(_target("secondary"), _bare_page()).action_id == "V-8"
