"""V-7: the page already answers questions and never says so in the markup.

The cheapest AI-visibility work there is — the answers are written, the
headings are there, and an engine assembling a response has to infer from
prose what FAQPage would have told it outright. Nothing covered it: V-2 only
fires when the question is absent, and mentions FAQPage as part of writing a
new block.
"""

from __future__ import annotations

import pytest

from app.decisions.catalog import PageFacts, prescribe, v7_mark_up_the_faq
from app.decisions.targets import Candidate, ScoredCandidate
from app.services.target_signals import _declares_faq, _has_faq_section, _is_question

QUESTIONS = ("How is carbon fibre made", "Why does it cost more?", "Is it recyclable?")


def _target() -> ScoredCandidate:
    return ScoredCandidate(
        candidate=Candidate(
            keyword="carbon fibre",
            target_url="/a",
            ranking_url="/a",
            position=8.0,
            volume=200.0,
        ),
        score=1.0,
        factors={},
    )


def _page(**kw) -> PageFacts:
    base = dict(url="/a", has_faq_section=True, has_faq_schema=False)
    base.update(kw)
    return PageFacts(**base)


def test_it_fires_on_questions_the_page_answers_without_markup():
    found = v7_mark_up_the_faq(_target(), _page())
    assert found is not None
    assert found.action_id == "V-7"
    assert "FAQ" in found.title
    assert "frequently asked questions" in found.why
    # Markup, not writing: the answers already exist.
    assert found.effort_min == 15
    assert found.metric_key == "ai_presence"


def test_it_stays_quiet_where_the_markup_is_already_there():
    assert v7_mark_up_the_faq(_target(), _page(has_faq_schema=True)) is None


def test_a_page_with_no_faq_section_is_left_alone():
    assert v7_mark_up_the_faq(_target(), _page(has_faq_section=False)) is None


def test_the_done_when_forbids_inventing_answers():
    found = v7_mark_up_the_faq(_target(), _page())
    assert "nothing that is not on the page" in found.done_when


def test_it_comes_before_the_page_rewrites():
    """Fifteen minutes of markup against a rewrite, on a page that needs
    both — cheapest first where the cheap thing is also the right thing."""
    # A page with no term in the title *and* an unmarked FAQ: V-1 still wins,
    # because a page that never says the phrase is the bigger problem.
    page = _page(title=None, description=None, headings=())
    assert prescribe(_target(), page).action_id in {"V-1", "V-7"}

    # With the term everywhere, the FAQ is what is left.
    covered = _page(
        title="carbon fibre",
        description="carbon fibre",
        headings=("carbon fibre",) + QUESTIONS,
    )
    assert prescribe(_target(), covered).action_id == "V-7"


# ── Reading the two halves ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ({"@type": "FAQPage"}, True),
        ({"@graph": [{"@type": "WebPage"}, {"@type": "FAQPage"}]}, True),
        ({"@type": ["WebPage", "QAPage"]}, True),
        # Walked rather than read off the top, for the same reason the
        # entity check is: an `@context` wrapper hides what is below it.
        ({"mainEntity": {"nested": {"@type": "FAQPage"}}}, True),
        ({"@type": "Article"}, False),
        ({}, False),
    ],
)
def test_faq_schema_is_found_anywhere_in_the_document(raw, expected):
    assert _declares_faq(raw) is expected


@pytest.mark.parametrize(
    "heading,is_question",
    [
        ("How is carbon fibre made", True),
        ("Is it recyclable?", True),
        ("What it costs", True),
        ("Our services", False),
        ("Carbon fibre panels", False),
    ],
)
def test_a_question_heading_is_what_a_visitor_reads_as_one(heading, is_question):
    assert _is_question(heading) is is_question


# ── Read, not inferred ──────────────────────────────────────────────────────


def test_an_faq_is_a_heading_that_says_so():
    """SMA's /capabilities/local-seo, verbatim.

    Two passes at inferring an FAQ from question-shaped headings were wrong
    in both directions here: they caught three marketing headings and missed
    the actual "Frequently asked questions" section, whose Q&A pairs sit in
    an accordion and so are not headings at all.
    """
    real_page = [
        {"heading": "Local SEO built to win the job"},
        {"heading": "Struggling with these local SEO challenges?"},
        {"heading": "Why choose SMA as your local SEO agency"},
        {"heading": "What our clients say about us"},
        {"heading": "Frequently asked questions"},
    ]
    assert _has_faq_section(real_page) is True
    # Without the last heading there is no FAQ on this page, whatever the
    # question marks suggest.
    assert _has_faq_section(real_page[:-1]) is False


@pytest.mark.parametrize(
    "heading,found",
    [
        ("Frequently asked questions", True),
        ("FAQ", True),
        ("FAQs", True),
        ("Common questions", True),
        ("Questions and answers", True),
        # Narrow on purpose: a page that says it has one does, and a page
        # that does not is a guess.
        ("Frequently", False),
        ("Ask us anything", False),
        ("Our services", False),
    ],
)
def test_the_heading_has_to_announce_an_faq(heading, found):
    assert _has_faq_section([{"heading": heading}]) is found
