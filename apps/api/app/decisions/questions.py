"""Questions a page draws, and whether it answers them.

Two rules read this. 3a asks whether the passage that answers a query
answers it *first* — a page can rank for a question, contain the answer
three paragraphs down, and lose the click to a result that leads with it.
3b asks which questions a page draws impressions for and does not cover at
all.

Both are judgements about wording, so both live here as pure functions
over text. Nothing in this module touches the database or the engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A query that reads as a question. The crawler matches headings the same
#: way, so a visible FAQ heading and a Search Console query are judged
#: alike — a page that answers "how long does it take" should not be told
#: to add an FAQ entry for the same words.
QUESTION_OPENERS = frozenset(
    "what how why when where which who can does do is are should".split()
)

#: Words that carry no subject. Overlap is measured without them, or every
#: query about anything would share "the" and "a" with every paragraph.
STOPWORDS = frozenset(
    """a an and are as at be but by can do does for from had has have how i if in
    is it its of on or should that the this to was what when where which who why
    will with you your""".split()
)

#: Openings that defer the answer. A paragraph that starts this way is
#: throat-clearing however good the rest of it is, and the reader who came
#: for the answer has already gone back to the results.
FILLER_OPENERS = (
    "in this article",
    "in this post",
    "in this guide",
    "in today's",
    "in todays",
    "welcome",
    "as mentioned",
    "as we discussed",
    "we often get asked",
    "have you ever",
    "let's face it",
    "lets face it",
)

#: Queries that want a supplier, not an explanation. An FAQ entry answering
#: "plumber near me" is not an answer, it is a landing page in the wrong
#: place, so 3b leaves them alone.
BOFU_TERMS = frozenset(
    {"near", "hire", "quote", "pricing", "price", "cost", "company", "agency", "services"}
)


def is_question(text: str) -> bool:
    """Whether a query or heading reads as a question."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    if stripped.endswith("?"):
        return True
    first = re.split(r"[^a-z']+", stripped.lower(), maxsplit=1)[0]
    return first in QUESTION_OPENERS


def tokens(text: str) -> frozenset[str]:
    """The words that say what something is about."""
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return frozenset(w for w in words if w and w not in STOPWORDS)


def token_overlap(query: str, candidate: str) -> float:
    """Share of the query's meaningful words that appear in the candidate.

    Directional on purpose: the question is whether the text covers the
    query, not whether the two are the same length. A thorough paragraph
    that answers a three-word query scores 1.0, which is right.
    """
    wanted = tokens(query)
    if not wanted:
        return 0.0
    return len(wanted & tokens(candidate)) / len(wanted)


def is_bofu(query: str) -> bool:
    return bool(tokens(query) & BOFU_TERMS)


def word_count(text: str) -> int:
    return len((text or "").split())


@dataclass(frozen=True)
class Section:
    """A heading and the paragraph under it, as the crawl stored them."""

    heading: str
    first_paragraph: str


def best_section_for(query: str, sections: list[Section]) -> Section | None:
    """The section whose heading is closest to the query.

    None when nothing comes close: answering a query the page never raises
    is a content decision, not a rewrite, and 3a has nothing to say about
    it.
    """
    best: Section | None = None
    best_score = 0.0
    for section in sections:
        score = token_overlap(query, section.heading)
        if score > best_score:
            best, best_score = section, score
    return best if best_score >= 0.5 else None


@dataclass(frozen=True)
class AnswerFirstResult:
    passes: bool
    reason: str
    heading: str | None = None


def answers_first(
    query: str,
    section: Section | None,
    *,
    min_words: int,
    max_words: int,
    min_overlap: float,
) -> AnswerFirstResult:
    """Whether the opening paragraph answers the query, and if not why.

    Three ways to fail, and the reason reaches the prescription, because
    "too long" and "does not mention the subject" are different edits.
    """
    if section is None:
        return AnswerFirstResult(False, "no_matching_heading")

    paragraph = section.first_paragraph or ""
    opening = paragraph.strip().lower()
    if any(opening.startswith(f) for f in FILLER_OPENERS):
        return AnswerFirstResult(False, "opens_with_filler", section.heading)

    count = word_count(paragraph)
    if count < min_words:
        return AnswerFirstResult(False, "too_short", section.heading)
    if count > max_words:
        return AnswerFirstResult(False, "too_long", section.heading)

    if token_overlap(query, paragraph) < min_overlap:
        return AnswerFirstResult(False, "does_not_answer", section.heading)

    return AnswerFirstResult(True, "answers_first", section.heading)


def uncovered_questions(
    queries: list[str], faq_questions: list[str], *, coverage_overlap: float
) -> list[str]:
    """Question queries the page's FAQ does not already answer.

    Commercial intent is excluded: an FAQ entry for "plumber near me" is a
    landing page in the wrong place, not an answer.
    """
    out: list[str] = []
    for query in queries:
        if not is_question(query) or is_bofu(query):
            continue
        if any(token_overlap(query, faq) >= coverage_overlap for faq in faq_questions):
            continue
        out.append(query)
    return out
