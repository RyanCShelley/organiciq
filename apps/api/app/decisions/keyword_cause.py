"""Why a tracked keyword does not rank, and which step failed. Playbook 7.

"Nothing ranks for this" is a fact, not a cause. The fix depends entirely
on which of five things is missing, and they are checked cheapest first:
a page that cannot be indexed will not rank however good it is, so there
is no point talking about subtopics until that is cleared.

Steps 3 and 5 of the playbook — format match against the top five, and the
authority gap against their referring domains — need SERP results we do
not store. Difficulty stands in for the authority question, because a term
nothing ranks for is usually a term that is hard to rank for, and the
format question is left to a human with the gap named.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.decisions.prescription import Prescription, Step

#: A page with fewer inbound internal links than this is not being put
#: forward by its own site, whatever else is true of it.
MIN_INTERNAL_LINKS = 3
#: Past this, winning the head term is a year's work and a long-tail
#: variant is the honest first target.
HARD_DIFFICULTY = 70.0


@dataclass(frozen=True)
class KeywordSignals:
    keyword: str
    volume: float
    difficulty: float | None
    #: The page Search Console already shows for the term, if any.
    page_url: str | None
    page_impressions: float = 0.0
    page_position: float | None = None
    #: From the crawl of that page. None where it was not crawled.
    indexable: bool | None = None
    canonical_elsewhere: bool = False
    in_sitemap: bool | None = None
    inbound_internal_links: int | None = None
    title: str | None = None


def _title_misses_keyword(title: str | None, keyword: str) -> bool:
    if not title:
        return False
    head = keyword.strip().lower()
    return head not in title.lower()


def classify_keyword_gap(signals: KeywordSignals) -> Prescription:
    evidence = {
        "keyword": signals.keyword,
        "volume": round(signals.volume),
        "difficulty": signals.difficulty,
        "page_url": signals.page_url,
        "page_impressions": round(signals.page_impressions),
        "page_position": signals.page_position,
    }

    # 1. No page at all. Everything else is moot, and this is the only case
    #    where "build a page" is the right instruction.
    if not signals.page_url:
        long_tail = signals.difficulty is not None and signals.difficulty >= HARD_DIFFICULTY
        steps = [
            Step(
                f"Write a page that targets “{signals.keyword}”",
                detail="Nothing on the site draws a single impression for it, so there "
                "is nothing to strengthen. Put the term in the title, the H1 and the "
                "first hundred words.",
            ),
            Step(
                "Link it from the service page and two related posts",
                detail="A new page with no internal links is not being put forward by "
                "its own site.",
            ),
        ]
        if long_tail:
            steps.append(
                Step(
                    "Target a long-tail variant first",
                    detail=f"Difficulty {signals.difficulty:.0f} means the head term is "
                    "a year of work. Win a narrower version, then widen.",
                    human=True,
                )
            )
        return Prescription(
            cause="undetermined",
            evidence={**evidence, "gap": "no_page"},
            steps=steps,
            expected_impact=f"the term's {signals.volume:,.0f} monthly searches, in part",
            verify_metric="keyword_position",
            verify_after_days=56,
        )

    # 2. The page exists and cannot rank. Fix that before anything else.
    blockers: list[str] = []
    if signals.indexable is False:
        blockers.append("it is not indexable")
    if signals.canonical_elsewhere:
        blockers.append("its canonical points at another page")
    if signals.in_sitemap is False:
        blockers.append("it is not in the sitemap")
    if signals.inbound_internal_links is not None and (
        signals.inbound_internal_links < MIN_INTERNAL_LINKS
    ):
        blockers.append(
            f"only {signals.inbound_internal_links} internal links point at it"
        )
    if blockers:
        return Prescription(
            cause="undetermined",
            evidence={**evidence, "gap": "page_cannot_rank", "blockers": blockers},
            steps=[
                Step(
                    "Clear what is stopping this page from ranking: " + "; ".join(blockers),
                    target=signals.page_url,
                    detail="No amount of content work moves a page that Google cannot "
                    "index or that the site does not link to.",
                ),
            ],
            expected_impact=f"the term's {signals.volume:,.0f} monthly searches, in part",
            verify_metric="keyword_position",
            verify_after_days=28,
        )

    # 3. The page can rank and does not. On-page is what is left that we can
    #    see; the rest needs the SERP, which is a human's job for now.
    steps = []
    if _title_misses_keyword(signals.title, signals.keyword):
        steps.append(
            Step(
                f"Put “{signals.keyword}” in the title and H1",
                target=signals.page_url,
                detail=f"The title currently reads “{signals.title}” and does "
                "not contain the term the page is meant to win.",
            )
        )
    steps.append(
        Step(
            "List the sections the top three results cover and this page does not",
            target=signals.page_url,
            detail="Those sections are the brief. The SERP is not stored, so this is "
            "the one step that needs a person.",
            human=True,
        )
    )
    if signals.difficulty is not None and signals.difficulty >= HARD_DIFFICULTY:
        steps.append(
            Step(
                "Target a long-tail variant alongside it",
                target=signals.page_url,
                detail=f"Difficulty {signals.difficulty:.0f}. The page can rank for a "
                "narrower version far sooner than for the head term.",
                human=True,
            )
        )

    position = (
        f" at position {signals.page_position:.0f}" if signals.page_position else ""
    )
    return Prescription(
        cause="undetermined",
        evidence={**evidence, "gap": "page_not_competitive"},
        steps=steps,
        expected_impact=(
            f"{signals.page_impressions:,.0f} impressions{position} that are not "
            "converting to rank"
        ),
        verify_metric="keyword_position",
        verify_after_days=56,
    )
