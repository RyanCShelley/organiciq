"""Why an answer engine does not cite us. Playbook 8.

The old rule said "win a citation for this prompt: the sources answer
engines currently cite are the brief" — which is true and is not a step,
because it does not say who those sources are or what to change.

Most of the playbook's checks need data that is not wired: who is cited
instead lives in SE Visible and is not ingested; whether the answer is
quotable needs the page body, which is not stored; entity consistency
needs the off-site profiles. Those become named human checks rather than
silence, which is what the spec asks for.

Two checks do have data, and they come first because they are absolute:
an engine that cannot fetch the page will never cite it, and a prompt with
no page behind it has nothing to cite.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.decisions.prescription import Prescription, Step


@dataclass(frozen=True)
class PromptSignals:
    prompt: str
    checks: int
    #: AI crawlers robots.txt turns away, from the site crawl.
    blocked_crawlers: tuple[str, ...] = ()
    #: The page on the site that best matches the prompt's wording, by
    #: shared terms with Search Console queries. None when nothing matches.
    best_page: str | None = None
    #: What that page is for. A commercial page answers the question in an
    #: FAQ; an article answers it in a section under its own heading. The
    #: same instruction on both reads as written by someone who had not
    #: looked at either.
    best_page_type: str | None = None
    #: Whether the engine stores who *is* cited for this prompt. False until
    #: SE Visible's citation layer is ingested.
    citations_known: bool = False


def classify_prompt_gap(signals: PromptSignals) -> Prescription:
    evidence = {
        "prompt": signals.prompt,
        "checks_in_period": signals.checks,
        "best_matching_page": signals.best_page,
    }

    # 1. The engines cannot read the site. Nothing else matters.
    if signals.blocked_crawlers:
        agents = ", ".join(signals.blocked_crawlers)
        return Prescription(
            cause="ai_crawlers_blocked",
            evidence={**evidence, "agents": list(signals.blocked_crawlers)},
            steps=[
                Step(
                    f"Allow {agents} in robots.txt",
                    detail="These agents fetch pages for answer engines. While they are "
                    "disallowed the site cannot be cited, however well it answers the "
                    "question. This is usually a plugin default rather than a decision.",
                ),
            ],
            expected_impact="Makes citation possible at all",
            verify_metric="ai_prompt_citations",
            verify_after_days=28,
        )

    # 2. Nothing on the site answers it.
    if not signals.best_page:
        return Prescription(
            cause="no_page_answers_prompt",
            evidence=evidence,
            steps=[
                Step(
                    "Write a page with this question as its H1",
                    detail=f"“{signals.prompt}” — open with a 40 to 60 word "
                    "answer directly under the heading, then the detail. Nothing on the "
                    "site currently matches the question's wording.",
                ),
                Step(
                    "Add three to five FAQs built from related prompts",
                    detail="Each as a question heading with a short direct answer, which "
                    "is the shape an engine can quote.",
                ),
            ],
            expected_impact="A citable answer where there is none",
            verify_metric="ai_prompt_citations",
            verify_after_days=42,
        )

    # 3. A page exists and is not being quoted. The reasons we can test for
    #    are exhausted, so the remaining checks are named rather than implied.
    # One page, one addition. Three steps on three parts of a page is a
    # morning's work, and a growth action is an hour.
    sells = signals.best_page_type in {"commercial", "conversion"}
    steps = [
        Step(
            (
                f"Add “{signals.prompt}” as an FAQ on this page, answered in "
                "the first two sentences"
            )
            if sells
            else (
                f"Add a section headed “{signals.prompt}”, opening with a "
                "direct answer"
            ),
            target=signals.best_page,
            detail="Engines quote the passage that answers the question as asked, so "
            "the heading has to match the wording rather than paraphrase it."
            + (
                " A buying page answers it briefly and gets back to the offer."
                if sells
                else " An article can answer it properly once the first two sentences"
                " have."
            ),
        ),
    ]
    if not signals.citations_known:
        steps.append(
            Step(
                "Read the answer engine's own output and note which sources it cites",
                detail="The citation layer is not ingested, so who is being cited "
                "instead cannot be read from our data. If they are third-party lists "
                "or review sites, the work is getting listed there, not on-page.",
                human=True,
            )
        )
    return Prescription(
        cause="page_not_quotable",
        evidence=evidence,
        steps=steps,
        expected_impact="A citation on this prompt",
        verify_metric="ai_prompt_citations",
        verify_after_days=42,
    )
