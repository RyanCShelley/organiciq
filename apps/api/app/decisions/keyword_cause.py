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
#: Below this, Search Console showing a page for the term is noise rather
#: than evidence the page targets it. The homepage picking up three
#: impressions for "seo services" does not make it the SEO services page,
#: and treating it as one sends someone to rewrite the wrong title.
MIN_IMPRESSIONS_FOR_PAGE_MATCH = 30.0


@dataclass(frozen=True)
class KeywordSignals:
    keyword: str
    volume: float
    difficulty: float | None
    #: The page Search Console already shows for the term, if any.
    page_url: str | None
    page_impressions: float = 0.0
    #: A page whose title targets the term, found by matching the crawl when
    #: Search Console has nothing substantial. `/capabilities/seo` exists and
    #: draws three impressions for "seo services", which is below the match
    #: threshold — without this the engine declares the page does not exist
    #: and asks someone to build it a second time.
    title_match_url: str | None = None
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
    has_gsc_page = bool(signals.page_url) and (
        signals.page_impressions >= MIN_IMPRESSIONS_FOR_PAGE_MATCH
    )
    target_url = signals.page_url if has_gsc_page else signals.title_match_url
    evidence = {
        "keyword": signals.keyword,
        "volume": round(signals.volume),
        "difficulty": signals.difficulty,
        "page_url": signals.page_url,
        "matched_page": target_url,
        "page_impressions": round(signals.page_impressions),
        "page_position": signals.page_position,
    }

    # 1. No page at all. Everything else is moot, and this is the only case
    #    where "build a page" is the right instruction.
    if not target_url:
        long_tail = signals.difficulty is not None and signals.difficulty >= HARD_DIFFICULTY
        # What was looked at, so the card never claims nothing exists while
        # printing an impression count beside it.
        if signals.page_url:
            seen = (
                f"The closest page is {signals.page_url}, drawing "
                f"{signals.page_impressions:,.0f} impressions for the term — too few to "
                "call it the page for it, and no page title targets it either. "
            )
        else:
            seen = (
                "No page draws an impression for it and no page title targets it. "
            )
        steps = [
            Step(
                f"Write a page that targets “{signals.keyword}”",
                detail=seen
                + "Put the term in the title, the H1 and the first hundred words.",
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
            cause="no_page_for_term",
            evidence=evidence,
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
            cause="page_cannot_rank",
            evidence={**evidence, "blockers": blockers},
            steps=[
                Step(
                    "Clear what is stopping this page from ranking: " + "; ".join(blockers),
                    target=target_url,
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
                target=target_url,
                detail=f"The title currently reads “{signals.title}” and does "
                "not contain the term the page is meant to win.",
            )
        )
    steps.append(
        Step(
            "List the sections the top three results cover and this page does not",
            target=target_url,
            detail="Those sections are the brief. The SERP is not stored, so this is "
            "the one step that needs a person.",
            human=True,
        )
    )
    if signals.difficulty is not None and signals.difficulty >= HARD_DIFFICULTY:
        steps.append(
            Step(
                "Target a long-tail variant alongside it",
                target=target_url,
                detail=f"Difficulty {signals.difficulty:.0f}. The page can rank for a "
                "narrower version far sooner than for the head term.",
                human=True,
            )
        )

    return Prescription(
        cause="page_not_competitive",
        evidence=evidence,
        steps=steps,
        expected_impact=(
            f"a share of the term's {signals.volume:,.0f} monthly searches, against "
            f"the {signals.page_impressions:,.0f} impressions this page draws for it now"
        ),
        verify_metric="keyword_position",
        verify_after_days=56,
    )
