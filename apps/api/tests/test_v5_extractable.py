"""V-5: the SERP lifts an answer and the page offers nothing liftable.

The last action in BLOCKED_ACTIONS, and it needed both halves. Without the
SERP there is nothing saying an answer is being lifted at all; without the
crawl's format flags every page looks unstructured, and V-5 would prescribe
a table for the whole site.
"""

from __future__ import annotations

import lxml.html as html
import pytest

from app.decisions.catalog import (
    BLOCKED_ACTIONS,
    PageFacts,
    SectionFacts,
    v5_add_an_extractable_structure,
)
from app.decisions.targets import Candidate, ScoredCandidate
from app.ingestion.crawler.parse import extract_sections

TERM = "how is carbon fibre made"


def _target(**kw) -> ScoredCandidate:
    base = dict(
        keyword=TERM,
        target_url="/a",
        ranking_url="/a",
        position=6.0,
        volume=400.0,
        serp_pulled=True,
        serp_features=frozenset({"ai_overview"}),
    )
    base.update(kw)
    return ScoredCandidate(candidate=Candidate(**base), score=1.0, factors={})


def _page(*sections: SectionFacts) -> PageFacts:
    return PageFacts(url="/a", sections=sections)


def _v5(target, page):
    return v5_add_an_extractable_structure(target, page)


# ── The crawler half ────────────────────────────────────────────────────────


def test_the_crawl_flags_what_an_engine_could_lift():
    doc = html.fromstring(
        """<div>
          <h2>How is carbon fibre made</h2><p>It is made by heating fibres.</p>
          <h2>Properties</h2><p>Tensile strength reaches 600 ksi.</p>
          <h2>Steps</h2><ul><li>one</li></ul>
          <h2>Costs</h2><table><tr><td>a</td></tr></table>
        </div>"""
    )
    by_heading = {s.heading: s for s in extract_sections(doc)}
    assert by_heading["How is carbon fibre made"].extractable is False
    assert by_heading["Properties"].has_stat is True
    assert by_heading["Steps"].has_list is True
    assert by_heading["Costs"].has_table is True


@pytest.mark.parametrize(
    "text,is_stat",
    [
        ("Tensile strength reaches 600 ksi.", True),
        ("It cuts cure time by 40%.", True),
        ("From $1,200 per panel.", True),
        ("Takes 3 hours to cure.", True),
        # Every copyright footer and blog date would otherwise be a figure.
        ("Copyright 2026 Acme Composites.", False),
        ("We make carbon fibre parts.", False),
    ],
)
def test_a_year_is_not_a_statistic(text: str, is_stat: bool):
    doc = html.fromstring(f"<div><h2>H</h2><p>{text}</p></div>")
    assert extract_sections(doc)[0].has_stat is is_stat


# ── The action ──────────────────────────────────────────────────────────────


def test_nothing_is_blocked_any_more():
    assert BLOCKED_ACTIONS == ()


def test_v5_fires_when_the_serp_lifts_and_the_section_is_prose():
    found = _v5(_target(), _page(SectionFacts(heading="How is carbon fibre made")))
    assert found is not None
    assert found.action_id == "V-5"
    assert "an AI Overview" in found.why
    assert found.check_after_days == 30


@pytest.mark.parametrize(
    "section",
    [
        SectionFacts(heading=TERM, has_table=True),
        SectionFacts(heading=TERM, has_list=True),
        SectionFacts(heading=TERM, has_stat=True),
    ],
)
def test_v5_stays_quiet_where_something_liftable_already_sits(section):
    assert _v5(_target(), _page(section)) is None


def test_v5_needs_the_serp_to_be_lifting_something():
    # A SERP with no AI Overview or snippet is not quoting anyone, so there
    # is nothing for a table to win.
    assert _v5(
        _target(serp_features=frozenset({"images", "local_pack"})),
        _page(SectionFacts(heading=TERM)),
    ) is None


def test_v5_says_nothing_before_a_serp_has_been_pulled():
    assert _v5(
        _target(serp_pulled=False, serp_features=frozenset()),
        _page(SectionFacts(heading=TERM)),
    ) is None


def test_v5_says_nothing_where_the_crawl_predates_the_flags():
    """An old crawl has no flags, and every page would read as unstructured."""
    assert _v5(_target(), PageFacts(url="/a", sections=())) is None


def test_v5_leaves_a_page_with_no_matching_heading_to_v2():
    # Nothing on the page asks the question. That is V-2's finding — adding
    # a table under a heading that does not exist is not an instruction.
    assert _v5(_target(), _page(SectionFacts(heading="About us"))) is None
