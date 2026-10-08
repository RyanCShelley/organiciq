"""Does the page answer the question it ranks for, and which does it miss.

A page can rank for a question, contain the answer three paragraphs down,
and lose the click to a result that leads with it. That is 3a. 3b is the
question a page draws impressions for and never addresses at all.
"""

from __future__ import annotations

import pytest

from app.decisions.questions import (
    Section,
    answers_first,
    best_section_for,
    is_bofu,
    is_question,
    token_overlap,
    uncovered_questions,
)

WORDS = {"min_words": 15, "max_words": 70, "min_overlap": 0.5}


# ── What counts as a question ──


@pytest.mark.parametrize(
    "text",
    [
        "how long does slab leak detection take",
        "What does it cost?",
        "can you detect a leak under a pool",
        "is a hydrostatic test worth it",
        "slab leak repair?",
    ],
)
def test_these_read_as_questions(text):
    assert is_question(text)


@pytest.mark.parametrize(
    "text",
    ["slab leak detection melbourne fl", "emergency plumber", "leak detection cost", ""],
)
def test_these_do_not(text):
    assert not is_question(text)


def test_a_trailing_question_mark_beats_the_opener_list():
    """Not every question starts with a question word, and a visitor who
    typed one is still asking."""
    assert is_question("slab leaks under a pool?")


# ── Overlap ──


def test_overlap_ignores_words_that_say_nothing():
    assert token_overlap("what is a slab leak", "a slab leak is water under concrete") == 1.0


def test_overlap_is_directional():
    """The question is whether the text covers the query, not whether the
    two are the same length — a thorough answer should score 1.0."""
    assert token_overlap("slab leak", "slab leak detection using acoustic tools") == 1.0
    assert token_overlap("slab leak detection acoustic", "slab leak") == 0.5


def test_a_query_of_nothing_but_stopwords_overlaps_nothing():
    assert token_overlap("is it the", "anything at all") == 0.0


# ── Which section answers it ──


SECTIONS = [
    Section("Slab leak detection", "We find leaks under concrete."),
    Section("What does slab leak detection cost?", "Most inspections are $350."),
    Section("Our guarantee", "We stand behind the work."),
]


def test_the_closest_heading_wins():
    found = best_section_for("what does slab leak detection cost", SECTIONS)
    assert found is not None and found.heading.startswith("What does slab")


def test_a_query_the_page_never_raises_matches_nothing():
    """Answering it is a content decision, not a rewrite. 3a has nothing to
    say about a question the page does not pose."""
    assert best_section_for("how do I replace a water heater", SECTIONS) is None


# ── The answer-first test ──


def test_a_direct_opening_passes():
    section = Section(
        "What does slab leak detection cost?",
        "Slab leak detection costs between $300 and $500 for most homes, and we "
        "quote the exact figure before any work begins on your property today.",
    )
    assert answers_first("what does slab leak detection cost", section, **WORDS).passes


def test_filler_fails_however_good_the_rest_is():
    section = Section(
        "What does slab leak detection cost?",
        "In this article we will explore the many factors affecting slab leak "
        "detection cost, including equipment, access and the age of the home.",
    )
    result = answers_first("what does slab leak detection cost", section, **WORDS)
    assert not result.passes
    assert result.reason == "opens_with_filler"


def test_too_short_to_be_an_answer():
    section = Section("What does it cost?", "It depends on the home.")
    result = answers_first("what does it cost", section, **WORDS)
    assert not result.passes and result.reason == "too_short"


def test_too_long_to_be_read_first():
    section = Section("What does it cost?", "cost " * 80)
    result = answers_first("what does it cost", section, **WORDS)
    assert not result.passes and result.reason == "too_long"


def test_on_topic_heading_with_an_off_topic_paragraph():
    section = Section(
        "What does slab leak detection cost?",
        "Our team has served Brevard County since 1998 and we are proud of the "
        "relationships we have built with homeowners across the whole region.",
    )
    result = answers_first("what does slab leak detection cost", section, **WORDS)
    assert not result.passes and result.reason == "does_not_answer"


def test_a_heading_with_no_paragraph_fails_rather_than_crashing():
    result = answers_first("what does it cost", Section("What does it cost?", ""), **WORDS)
    assert not result.passes and result.reason == "too_short"


def test_no_matching_heading_is_its_own_reason():
    result = answers_first("something else entirely", None, **WORDS)
    assert not result.passes and result.reason == "no_matching_heading"


@pytest.mark.parametrize("count,expected", [(14, False), (15, True), (70, True), (71, False)])
def test_the_word_bounds_are_inclusive(count, expected):
    """Boundaries, because a rule that fires at 71 words and not 70 is a
    rule someone will argue with."""
    section = Section("What does it cost", "cost " * count)
    assert answers_first("what does it cost", section, **WORDS).passes is expected


# ── What the FAQ does not cover ──


def test_a_question_the_faq_answers_is_covered():
    assert uncovered_questions(
        ["how long does it take"], ["How long does it take?"], coverage_overlap=0.7
    ) == []


def test_a_question_nothing_answers_is_offered():
    assert uncovered_questions(
        ["how long does it take"], ["Do you repair the slab?"], coverage_overlap=0.7
    ) == ["how long does it take"]


def test_a_query_that_is_not_a_question_is_not_an_faq_entry():
    assert uncovered_questions(["slab leak detection cost"], [], coverage_overlap=0.7) == []


def test_a_buying_query_is_left_alone():
    """An FAQ entry for "plumber near me" is a landing page in the wrong
    place, not an answer."""
    assert uncovered_questions(
        ["who is the best plumber near me"], [], coverage_overlap=0.7
    ) == []
    assert is_bofu("what does it cost to hire an agency")


def test_partial_wording_still_counts_as_covered():
    """The FAQ says it differently. Offering to add the same question in
    other words is how a tool loses trust."""
    assert uncovered_questions(
        ["how long does slab leak detection take"],
        ["How long does slab leak detection usually take on a single-storey home?"],
        coverage_overlap=0.7,
    ) == []
