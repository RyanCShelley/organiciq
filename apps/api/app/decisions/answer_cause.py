"""What to write, for a page that ranks for a question and buries the answer.

Two prescriptions. 3a rewrites an opening that exists; 3b adds questions
the page draws and never addresses. Both are an hour or less and both name
the exact words, because "improve the content" is the sentence this engine
exists to stop producing.
"""

from __future__ import annotations

from app.decisions.prescription import Prescription, Step
from app.decisions.questions import AnswerFirstResult

#: Why the opening failed, and what to do about each. The reason reaches
#: the step, because "too long" and "does not mention the subject" are
#: different edits and sending the same sentence for both wastes the hour.
_WHY: dict[str, str] = {
    "opens_with_filler": (
        "It opens by announcing what the page will cover. A reader who searched "
        "this question has already got the answer somewhere else by the time "
        "that sentence ends."
    ),
    "too_short": (
        "It is too short to be the answer, so the reader has to keep going to "
        "find out whether the page is worth reading."
    ),
    "too_long": (
        "The answer is in there, but not in the first few lines. Lead with it "
        "and keep the detail underneath."
    ),
    "does_not_answer": (
        "The opening is about something else, so a reader who searched this "
        "question cannot tell the page answers it."
    ),
    "no_matching_heading": (
        "No heading on the page poses this question, so there is nothing for "
        "the answer to sit under."
    ),
}


def prescribe_answer_first(
    *,
    page_url: str,
    query: str,
    result: AnswerFirstResult,
    impressions: float,
    position: float,
    min_words: int,
    max_words: int,
) -> Prescription:
    """3a — rewrite the opening under the heading that answers the query."""
    heading = result.heading or query
    why = _WHY.get(result.reason, _WHY["does_not_answer"])

    steps = [
        Step(
            f"Rewrite the first paragraph under “{heading}” to answer "
            f"“{query}” in its first sentence",
            target=page_url,
            detail=(
                f"{why} Keep it between {min_words} and {max_words} words, use the "
                "words someone searching would use, and put the detail after it."
            ),
        )
    ]
    if result.reason == "no_matching_heading":
        steps = [
            Step(
                f"Add a heading that asks “{query}”, with the answer directly beneath it",
                target=page_url,
                detail=(
                    f"The page already draws {int(impressions):,} impressions for this "
                    f"question at position {position:.1f}. Nothing on the page poses it, "
                    "so the answer has nowhere to sit."
                ),
            )
        ]

    return Prescription(
        cause="answer_buried",
        evidence={
            "query": query,
            "heading": result.heading,
            "why": result.reason,
            "impressions": round(float(impressions), 1),
            "position": round(float(position), 1),
        },
        steps=steps,
        expected_impact="The clicks the ranking already earns but does not convert into visits",
        verify_metric="page_ctr_percent",
        verify_after_days=28,
    )


def prescribe_faq_expansion(
    *,
    page_url: str,
    questions: list[tuple[str, float, float]],
) -> Prescription:
    """3b — add the questions the page draws and does not answer.

    `questions` is (query, impressions, position), best first.
    """
    if not questions:
        raise ValueError("an FAQ expansion with no questions is a diagnosis")

    steps = [
        Step(
            f"Add “{query}” as an FAQ entry, answered in two sentences",
            target=page_url,
            detail=(
                f"{int(impressions):,} impressions at position {position:.1f} and nothing "
                "on the page answers it. Use the question as the heading, word for word."
            ),
        )
        for query, impressions, position in questions
    ]
    steps.append(
        Step(
            "Mark the new entries up as FAQPage so engines can quote them",
            target=page_url,
            detail="A visitor sees the heading either way; an engine needs the markup.",
        )
    )

    return Prescription(
        cause="questions_not_covered",
        evidence={
            "questions": [q for q, _i, _p in questions],
            "impressions": round(sum(i for _q, i, _p in questions), 1),
        },
        steps=steps,
        expected_impact="The clicks these questions already rank for and lose",
        verify_metric="page_ctr_percent",
        verify_after_days=28,
    )
