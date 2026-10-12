"""The action catalog: what to actually do about a scored target.

Twelve actions with stable ids. Within a branch, the first action whose
trigger fires for a target is the one prescribed — so a page missing the term
from its title gets V-1 rather than V-4, because putting the term on the page
comes before pointing links at it.

Every action names a page, says what "done" looks like, and carries the
metric it will be judged on and when. "Improve the content" is the sentence
this module exists to stop producing: a prescription nobody can tell you have
finished is a prescription nobody finishes.

Two of the twelve cannot fire yet. V-5 and T-2 both need the full SERP
feature list — which features a query shows, not just the ones the client
already holds — and that is a pull we do not make. They are defined here with
their trigger and skipped with a named reason, so the gap is visible on the
page rather than being an action that silently never appears.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.decisions.page_targets import PageCandidate
from app.decisions.slots import Prescription
from app.decisions.targets import ScoredCandidate
from app.decisions.triage import Branch


@dataclass(frozen=True)
class PageFacts:
    """What the crawl knows about the page a target is mapped to."""

    url: str
    title: str | None = None
    description: str | None = None
    headings: tuple[str, ...] = ()
    faq_questions: tuple[str, ...] = ()
    #: Entity markup present on the page: `about`, `mentions`, `sameAs`.
    entity_properties: frozenset[str] = frozenset()
    inbound_editorial_links: int = 0
    #: The site's median, so "under-linked" is relative to this site.
    site_median_links: float = 0.0
    page_type: str | None = None


@dataclass(frozen=True)
class SkippedAction:
    action_id: str
    reason: str


#: Why an action cannot fire, named rather than silent.
NO_SERP_FEATURES = (
    "needs the full SERP feature list for the query, which is not pulled — "
    "only features the client already holds are stored"
)


def _terms(text: str | None) -> set[str]:
    import re

    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2}


def _mentions(term: str, text: str | None) -> bool:
    """Whether the text uses the term, phrase-aware.

    A bag of words matches "agency seo local" to "local seo agency", which is
    how a page that never says the phrase was reported as already optimised
    for it.
    """
    if not text:
        return False
    return term.strip().lower() in text.strip().lower()


# ── Visibility ──────────────────────────────────────────────────────────────


def v1_term_in_high_value_spots(
    target: ScoredCandidate, page: PageFacts
) -> Prescription | None:
    """The term is missing from the title, the meta, or every heading."""
    term = target.candidate.keyword
    in_title = _mentions(term, page.title)
    in_description = _mentions(term, page.description)
    in_headings = any(_mentions(term, h) for h in page.headings)
    if in_title and in_description and in_headings:
        return None

    missing = [
        label
        for label, present in (
            ("the title", in_title),
            ("the meta description", in_description),
            ("any heading", in_headings),
        )
        if not present
    ]
    # "the title, the meta description, any heading" is a list read aloud by
    # a machine. The last one takes an "or".
    missing_text = (
        missing[0]
        if len(missing) == 1
        else " or ".join([", ".join(missing[:-1]), missing[-1]])
    )
    return Prescription(
        action_id="V-1",
        title=f"Put “{term}” in the title, a heading and the first 100 words",
        branch=Branch.VISIBILITY,
        target_url=page.url,
        term=term,
        score=target.score,
        effort_min=30,
        why=(
            f"The page is mapped to “{term}” and does not use it in "
            f"{missing_text}. A page that never says the phrase is asking a "
            "search engine to infer it."
        ),
        done_when=(
            f"“{term}” appears in the title tag, in one H2, and in the first "
            "100 words, reading as a sentence rather than an insertion."
        ),
        metric="Term position",
        evidence=(
            f"keyword_targets: {term} -> {page.url}",
            f"crawl: missing from {missing_text}",
        ),
    )


def v2_answer_block(target: ScoredCandidate, page: PageFacts) -> Prescription | None:
    """A question the page draws and does not answer."""
    term = target.candidate.keyword
    if not term.lower().startswith(
        ("what", "how", "why", "when", "where", "who", "is ", "are ", "can ", "does ")
    ):
        return None
    if any(_mentions(term, q) for q in page.faq_questions):
        return None
    return Prescription(
        action_id="V-2",
        title=f"Add an answer block for “{term}”",
        branch=Branch.VISIBILITY,
        target_url=page.url,
        term=term,
        score=target.score,
        effort_min=45,
        why=(
            f"The page is mapped to “{term}” and poses no heading that asks "
            "it, so there is nothing for an answer to sit under and nothing "
            "for an engine to quote."
        ),
        done_when=(
            "A heading asks the question word for word, a 40 to 60 word "
            "answer sits directly under it, and the pair is marked up as "
            "FAQPage."
        ),
        metric="Brand mention or citation",
        evidence=(f"crawl: {len(page.faq_questions)} questions on the page, none matching",),
    )


def v3_entity_markup(target: ScoredCandidate, page: PageFacts) -> Prescription | None:
    """No `about` or `mentions` tying the page to the term's subject."""
    if {"about", "mentions"} & page.entity_properties:
        return None
    return Prescription(
        action_id="V-3",
        title=f"Add entity markup naming the subject of “{target.candidate.keyword}”",
        branch=Branch.VISIBILITY,
        target_url=page.url,
        term=target.candidate.keyword,
        score=target.score,
        effort_min=30,
        why=(
            "The page carries no `about` or `mentions`, so nothing in the "
            "markup says what it is about. An engine assembling an answer has "
            "to infer the subject from prose."
        ),
        done_when=(
            "`about` and `mentions` name the subject, with a Wikidata "
            "`sameAs` where one exists."
        ),
        metric="Term position and AI citation",
        evidence=(f"facts_crawl_page_schema: {sorted(page.entity_properties) or 'no entity properties'}",),
    )


def v4_internal_links(target: ScoredCandidate, page: PageFacts) -> Prescription | None:
    """Fewer in-content links than the site's own median."""
    if page.site_median_links <= 0:
        return None
    if page.inbound_editorial_links >= page.site_median_links:
        return None
    return Prescription(
        action_id="V-4",
        title=f"Add internal links to the page that owns “{target.candidate.keyword}”",
        branch=Branch.VISIBILITY,
        target_url=page.url,
        term=target.candidate.keyword,
        score=target.score,
        effort_min=30,
        why=(
            f"{page.inbound_editorial_links} in-content links point here, "
            f"against a site median of {page.site_median_links:.0f}. Navigation "
            "does not count: it is on every page and says nothing about this one."
        ),
        done_when=(
            "Two or three in-content links from related pages, with the term "
            "or a variant as the anchor."
        ),
        metric="Term position",
        evidence=(
            f"facts_crawl_internal_links: {page.inbound_editorial_links} editorial "
            f"inbound, site median {page.site_median_links:.0f}",
        ),
    )


def v6_rehoming(target: ScoredCandidate, page: PageFacts) -> Prescription | None:
    """The term ranks on a page that is not the one it is mapped to."""
    if not target.rehoming:
        return None
    candidate = target.candidate
    return Prescription(
        action_id="V-6",
        title=f"Decide which page should own “{candidate.keyword}”",
        branch=Branch.VISIBILITY,
        target_url=candidate.target_url or page.url,
        term=candidate.keyword,
        score=target.score,
        effort_min=15,
        why=(
            f"“{candidate.keyword}” is mapped to {candidate.target_url} and "
            f"ranks on {candidate.ranking_url}. Optimising either one before "
            "that is settled is work on a page nobody chose."
        ),
        done_when=(
            "A decision is recorded: keep the mapping and move the ranking, "
            "change the mapping, or build a page for it."
        ),
        metric="Decision only",
        evidence=(
            f"keyword_targets: {candidate.target_url}",
            f"facts_ser_keywords ranking_url: {candidate.ranking_url}",
        ),
        flags=("no_target_mapping",) if not candidate.target_url else (),
    )


#: In order. The first whose trigger fires is the one prescribed: putting the
#: term on the page comes before pointing links at it.
VISIBILITY_ACTIONS: tuple[Callable[[ScoredCandidate, PageFacts], Prescription | None], ...] = (
    v6_rehoming,
    v1_term_in_high_value_spots,
    v2_answer_block,
    v3_entity_markup,
    v4_internal_links,
)

#: Defined, and unable to fire. Kept here so the gap is visible rather than
#: being an action that silently never appears.
BLOCKED_ACTIONS: tuple[SkippedAction, ...] = (
    SkippedAction("V-5", NO_SERP_FEATURES),
    SkippedAction("T-2", NO_SERP_FEATURES),
)


def prescribe(
    target: ScoredCandidate,
    page: PageFacts,
    *,
    actions: tuple[Callable[[ScoredCandidate, PageFacts], Prescription | None], ...]
    | None = None,
) -> Prescription | None:
    """The first action whose trigger fires for this target."""
    for action in actions or VISIBILITY_ACTIONS:
        found = action(target, page)
        if found is not None:
            return found
    return None


def prescribe_all(
    targets: list[tuple[ScoredCandidate, PageFacts]],
    **kwargs: Any,
) -> list[Prescription]:
    """One prescription per target, in the order the targets were ranked."""
    out: list[Prescription] = []
    for target, page in targets:
        found = prescribe(target, page, **kwargs)
        if found is not None:
            out.append(found)
    return out


# ── Traffic ─────────────────────────────────────────────────────────────────
#
# These take a page rather than a term. A traffic problem is a property of a
# page — the clicks it did not earn, the readers who left — and squeezing it
# through a keyword candidate would name a term in an action that is not
# about one.

#: Where a missed click is the snippet's fault rather than the position's.
#: Below the top three, a CTR under the curve is mostly explained by rank, so
#: a title rewrite would be sold on a number it cannot move. Held at three
#: because the spec says three, not because three makes it fire.
SNIPPET_MAX_POSITION = 3.0

#: Under this many impressions a CTR gap is a handful of searches, and the
#: curve is noise at that size.
MIN_IMPRESSIONS = 100.0

#: Enough sessions for an engagement rate to mean anything.
MIN_SESSIONS_FOR_ENGAGEMENT = 50.0


def t1_rewrite_snippet(page: PageCandidate) -> Prescription | None:
    """Top-three page earning fewer clicks than its position should."""
    missed = page.missed_clicks
    if (
        missed is None
        or page.position is None
        or page.position > SNIPPET_MAX_POSITION
        or page.impressions < MIN_IMPRESSIONS
        or missed < 1
        # A query naming the site is navigation. The shortfall is real and
        # the snippet is not the cause, so this would be a rewrite sold on a
        # number it cannot move.
        or page.top_query_is_navigational
    ):
        return None
    return Prescription(
        action_id="T-1",
        title="Rewrite the title and meta description",
        branch=Branch.TRAFFIC,
        target_url=page.url,
        term=page.top_query,
        score=missed,
        effort_min=30,
        why=(
            f"The page averages position {page.position:.1f} and earned "
            f"{page.clicks:.0f} clicks from {page.impressions:.0f} "
            f"impressions. The measured curve puts a page at that position on "
            f"{page.expected_clicks:.0f}. At the top of the page one, what is "
            "left to explain the gap is the snippet."
        ),
        done_when=(
            "The title is 60 characters or fewer, carries the term and a "
            "reason to click that the page delivers, and the old version is "
            "logged so the check has something to compare."
        ),
        metric="Clicks against the curve's expectation",
        evidence=(
            f"facts_gsc_pages: {page.clicks:.0f} clicks, "
            f"{page.impressions:.0f} impressions, position {page.position:.1f}",
            f"ctr_curve: {page.expected_clicks:.0f} clicks expected at that position",
        ),
    )


def t3_realign_to_the_audience(page: PageCandidate) -> Prescription | None:
    """People arrive and leave: engagement under the site's own median."""
    rate = page.engagement_rate
    if (
        rate is None
        or page.site_median_engagement is None
        or page.sessions < MIN_SESSIONS_FOR_ENGAGEMENT
        or rate >= page.site_median_engagement
    ):
        return None
    return Prescription(
        action_id="T-3",
        title="Rewrite the opening for the reader the page actually draws",
        branch=Branch.TRAFFIC,
        target_url=page.url,
        term=page.top_query,
        score=page.sessions * (page.site_median_engagement - rate),
        effort_min=60,
        why=(
            f"{page.sessions:.0f} sessions landed here and "
            f"{rate * 100:.0f}% engaged, against a site median of "
            f"{page.site_median_engagement * 100:.0f}%. The page is winning "
            "the click and losing the reader, which is a mismatch between "
            "what the search promised and what the opening delivers."
        ),
        done_when=(
            "The H1 and the first two paragraphs answer the query the page "
            "draws, in the words of the customer it is for, with the old "
            "opening logged."
        ),
        metric="Engaged session rate",
        evidence=(
            f"facts_ga4_traffic: {page.sessions:.0f} sessions, "
            f"{rate * 100:.0f}% engaged",
            f"site median engagement {page.site_median_engagement * 100:.0f}%",
        ),
    )


TRAFFIC_ACTIONS: tuple[Callable[[PageCandidate], Prescription | None], ...] = (
    t1_rewrite_snippet,
    t3_realign_to_the_audience,
)


# ── Leads ───────────────────────────────────────────────────────────────────
#
# Every one of these needs a confirmed funnel stage. A lead action on a page
# whose stage was guessed from its URL is the mistake `client_conversion_pages`
# was built to stop, so a page with no confirmed stage gets none of them.

#: Which offers suit a reader at each stage. A reader still learning is not
#: sent to a quote form; one ready to buy is not sent to another guide.
STAGE_FIT = {
    "tofu": ("tofu", "mofu"),
    "mofu": ("mofu", "bofu"),
    "bofu": ("bofu",),
}


#: How each stage reads in a sentence, so the reason is English rather than
#: an acronym the reader has to decode.
STAGE_WORDS = {
    "tofu": "still learning",
    "mofu": "comparing options",
    "bofu": "ready to buy",
}


def l1_route_to_the_next_step(page: PageCandidate) -> Prescription | None:
    """A page people land on with no in-content way forward."""
    if page.stage is None or page.stage == "bofu" or page.routes_onward:
        return None
    # The destination does not need a route to a destination.
    if page.is_conversion_page or not page.matched_offers:
        return None
    return Prescription(
        action_id="L-1",
        title="Add an in-content route to the next step",
        branch=Branch.LEADS,
        target_url=page.url,
        term=None,
        score=page.sessions,
        effort_min=30,
        why=(
            f"{page.sessions:.0f} sessions land here and the page carries no "
            "in-content link to any declared conversion page. Navigation and "
            "the footer do not count: they are on every page and say nothing "
            "about this one, so the reader is left to go looking."
        ),
        done_when=(
            f"An in-content link to {page.matched_offers[0]}, with a sentence "
            "saying what the reader gets by following it, placed where the "
            "page has finished answering what they came for."
        ),
        metric="Leads from sessions starting on this page",
        evidence=(
            f"facts_crawl_internal_links: no in-content link to a conversion page",
            f"facts_ga4_traffic: {page.sessions:.0f} sessions",
            f"client_page_stages: {page.stage}",
        ),
        check_after_days=30,
    )


def l2_add_a_call_to_action(page: PageCandidate) -> Prescription | None:
    """The page routes onward and never asks."""
    if page.stage is None or page.conversion_elements is None:
        return None
    if page.conversion_elements > 0:
        return None
    return Prescription(
        action_id="L-2",
        title="Add a call to action the page is missing",
        branch=Branch.LEADS,
        target_url=page.url,
        term=None,
        score=page.sessions,
        effort_min=30,
        why=(
            f"The crawl found no form or call to action on a page taking "
            f"{page.sessions:.0f} sessions. Whatever the reader decides here, "
            "the page gives them no way to act on it."
        ),
        done_when=(
            "One call to action on the first screen, worded for what this "
            "page is about rather than the site's standard line."
        ),
        metric="Lead rate for sessions landing on this page",
        evidence=(
            "facts_crawl_page_snapshots: conversion_elements = 0",
            f"facts_ga4_traffic: {page.sessions:.0f} sessions",
        ),
        check_after_days=30,
        # The crawl counts these and does not say where they sit, so "none in
        # the first screen" cannot be judged — only "none at all".
        flags=("cta_position_unknown",),
    )


def l3_match_the_offer_to_the_reader(page: PageCandidate) -> Prescription | None:
    """Every route out goes somewhere the reader is not ready for."""
    if page.stage is None or not page.routes_onward or not page.matched_offers:
        return None
    if page.is_conversion_page:
        return None
    # "generic" is an offer nobody gave a stage. It suits any reader by
    # definition — `matched_offers` already counts it as a match — so a page
    # linking to one is not pointing its reader somewhere wrong. Without this
    # L-3 would tell somebody to link to the page they already link to.
    fits = set(STAGE_FIT.get(page.stage, ())) | {"generic"}
    if page.linked_offer_stages & fits:
        return None
    linked = ", ".join(sorted(page.linked_offer_stages)) or "none"
    return Prescription(
        action_id="L-3",
        title="Point the page at an offer its reader is ready for",
        branch=Branch.LEADS,
        target_url=page.url,
        term=None,
        score=page.sessions,
        effort_min=30,
        why=(
            f"The reader here is {STAGE_WORDS[page.stage]}, and every "
            f"in-content route out goes to a {linked} offer. A declared offer "
            "that suits them exists and nothing links to it."
        ),
        done_when=(
            f"The in-content route points at {page.matched_offers[0]}, with "
            "the link text rewritten for what that offer gives this reader."
        ),
        metric="Lead rate for sessions landing on this page",
        evidence=(
            f"client_page_stages: {page.stage}",
            f"linked offer stages: {linked}",
            f"a matching offer exists: {page.matched_offers[0]}",
        ),
        check_after_days=45,
    )


LEAD_ACTIONS: tuple[Callable[[PageCandidate], Prescription | None], ...] = (
    l1_route_to_the_next_step,
    l2_add_a_call_to_action,
    l3_match_the_offer_to_the_reader,
)


def prescribe_page(
    page: PageCandidate,
    *,
    actions: tuple[Callable[[PageCandidate], Prescription | None], ...],
) -> Prescription | None:
    """The first action whose trigger fires for this page."""
    for action in actions:
        found = action(page)
        if found is not None:
            return found
    return None
