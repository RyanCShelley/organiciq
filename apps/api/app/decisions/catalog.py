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
class SectionFacts:
    """One heading, and whether an engine could lift anything under it."""

    heading: str
    has_table: bool = False
    has_list: bool = False
    has_stat: bool = False

    @property
    def extractable(self) -> bool:
        return self.has_table or self.has_list or self.has_stat


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
    #: The page has a section that announces itself as an FAQ.
    #:
    #: Read off a heading that says so, not inferred from question-shaped
    #: headings. Two passes at inferring it were wrong in both directions on
    #: SMA's /capabilities/local-seo: it caught "Struggling with these local
    #: SEO challenges?", "Why choose SMA as your local SEO agency" and "What
    #: our clients say about us" — all marketing — and missed the actual
    #: "Frequently asked questions" section, whose Q&A pairs are an
    #: accordion and so are not headings at all.
    has_faq_section: bool = False
    #: The page carries an FAQPage or QAPage block.
    has_faq_schema: bool = False
    #: Headings with their format flags, for V-5. Empty where the crawl
    #: predates the capture — which is why V-5 says nothing rather than
    #: reporting every page as unstructured.
    sections: tuple[SectionFacts, ...] = ()
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
    """A primary term missing from the title, the meta, or every heading.

    Primary only. A page has one title and it belongs to the term the page
    is *for*: telling somebody to put a secondary term in it is telling them
    to take the primary term out, and the engine would then find that
    missing next month and ask for it back.
    """
    if target.candidate.term_role == "secondary":
        return None
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
        metric_key="term_position",
        evidence=(
            f"keyword_targets: {term} -> {page.url}",
            f"crawl: missing from {missing_text}",
        ),
    )


def v8_secondary_term_section(
    target: ScoredCandidate, page: PageFacts
) -> Prescription | None:
    """A secondary term the page never gives a heading to.

    The counterpart to V-1. A secondary term does not earn the title — that
    is the primary term's — but it does earn a passage of its own, because
    a term mentioned nowhere in the structure is a term the page is not
    really about.
    """
    candidate = target.candidate
    if candidate.term_role != "secondary":
        return None
    term = candidate.keyword
    if any(_mentions(term, heading) for heading in page.headings):
        return None
    return Prescription(
        action_id="V-8",
        title=f"Give “{term}” a section of its own",
        branch=Branch.VISIBILITY,
        target_url=page.url,
        term=term,
        score=target.score,
        effort_min=45,
        why=(
            f"“{term}” is a secondary term for this page and no heading on it "
            "says so. The title belongs to the page's primary term, so this "
            "one earns a passage rather than a rewrite — and right now it has "
            "neither."
        ),
        done_when=(
            f"An H2 carrying “{term}”, with two or three paragraphs under it "
            "that answer what somebody searching that phrase came for. The "
            "title and H1 are left alone."
        ),
        metric="Term position",
        metric_key="term_position",
        evidence=(
            f"keyword_targets: {term} is secondary on {page.url}",
            f"crawl: none of {len(page.headings)} headings use it",
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
        metric_key="ai_presence",
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
        metric_key="term_position",
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
        metric_key="term_position",
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
        metric_key="decision",
        evidence=(
            f"keyword_targets: {candidate.target_url}",
            f"facts_ser_keywords ranking_url: {candidate.ranking_url}",
        ),
        flags=("no_target_mapping",) if not candidate.target_url else (),
    )





def v7_mark_up_the_faq(
    target: ScoredCandidate, page: PageFacts
) -> Prescription | None:
    """The page already answers questions and never says so in the markup.

    The cheapest AI-visibility work there is: the answers are written, the
    headings are there, and an engine assembling a response has to infer
    from prose what FAQPage would have told it outright. No new content.
    """
    if page.has_faq_schema or not page.has_faq_section:
        return None
    return Prescription(
        action_id="V-7",
        title="Mark up the FAQ this page already has",
        branch=Branch.VISIBILITY,
        target_url=page.url,
        term=target.candidate.keyword,
        score=target.score,
        effort_min=15,
        why=(
            "The page carries a section headed as frequently asked questions "
            "and no FAQPage markup. The answers are already written; nothing "
            "tells an engine assembling a response that they are answers."
        ),
        done_when=(
            "FAQPage markup lists every question in that section with the "
            "answer the page already gives, word for word, and nothing that "
            "is not on the page."
        ),
        metric="Brand mention or citation",
        metric_key="ai_presence",
        evidence=(
            "facts_crawl_page_snapshots: a heading announcing an FAQ",
            "facts_crawl_page_schema: no FAQPage block",
        ),
        check_after_days=30,
    )


def v5_add_an_extractable_structure(
    target: ScoredCandidate, page: PageFacts
) -> Prescription | None:
    """The SERP lifts an answer, and this page offers nothing liftable.

    Both halves are required. Without the SERP there is nothing saying an
    answer is being lifted at all; without the crawl's format flags every
    page looks unstructured, which would prescribe a table for the whole
    site.
    """
    candidate = target.candidate
    if not candidate.serp_pulled:
        return None
    lifted = {f for f in candidate.serp_features if f in EXTRACTIVE_FEATURES}
    if not lifted:
        return None
    if not page.sections:
        return None

    term = candidate.keyword
    matching = [s for s in page.sections if _mentions(term, s.heading)]
    # No heading asks the query: that is V-2's finding, not this one.
    if not matching:
        return None
    if any(s.extractable for s in matching):
        return None

    feature = sorted(lifted)[0]
    return Prescription(
        action_id="V-5",
        title=f"Add something liftable under the heading for “{term}”",
        branch=Branch.VISIBILITY,
        target_url=page.url,
        term=term,
        score=target.score,
        effort_min=45,
        why=(
            f"The results for “{term}” carry {EXTRACTIVE_FEATURES[feature]}, "
            "so an engine is lifting an answer from somewhere. The heading "
            "that asks it on this page is followed by prose and nothing "
            "else — no table, no list, no figure to quote."
        ),
        done_when=(
            "A table, a bullet summary or a stat block sits directly under "
            "that heading, answering the question on its own without the "
            "paragraph around it."
        ),
        metric="Term position and AI citation",
        metric_key="term_position",
        evidence=(
            f"facts_serp_features: {feature} present",
            f"facts_crawl_page_snapshots: no table, list or figure under "
            f"{len(matching)} matching heading(s)",
        ),
        check_after_days=30,
    )


#: Features that quote a passage off the page. These are the ones a liftable
#: structure can win; an image pack or a video result cannot be won with a
#: table.
EXTRACTIVE_FEATURES = {
    "ai_overview": "an AI Overview",
    "featured_snippet": "a featured snippet",
}


#: In order. The first whose trigger fires is the one prescribed: putting the
#: term on the page comes before pointing links at it.
VISIBILITY_ACTIONS: tuple[Callable[[ScoredCandidate, PageFacts], Prescription | None], ...] = (
    v6_rehoming,
    v1_term_in_high_value_spots,
    # Beside V-1, not after it: the two never both fire, because a term is
    # either the page's primary or one of its secondaries.
    v8_secondary_term_section,
    v2_answer_block,
    # Before the rest: the answers are already written, so this is fifteen
    # minutes of markup against a page rewrite. Cheapest first where the
    # cheap thing is also the right thing.
    v7_mark_up_the_faq,
    # Before V-3 and V-4: when an engine is visibly lifting an answer,
    # giving it something to lift beats marking up or linking to a page it
    # cannot quote.
    v5_add_an_extractable_structure,
    v3_entity_markup,
    v4_internal_links,
)

#: Nothing is blocked. V-5 was the last, and needed two things: the full
#: SERP feature list, now pulled from DataForSEO, and per-section table,
#: list and figure flags, now captured by the crawler. Kept as an empty
#: tuple rather than deleted, because the next action that cannot fire
#: should say so here rather than silently never appearing.
BLOCKED_ACTIONS: tuple[SkippedAction, ...] = ()


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
        metric_key="page_clicks",
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
        metric_key="engagement_rate",
        evidence=(
            f"facts_ga4_traffic: {page.sessions:.0f} sessions, "
            f"{rate * 100:.0f}% engaged",
            f"site median engagement {page.site_median_engagement * 100:.0f}%",
        ),
    )


#: The features worth a growth action, and how each reads in a sentence. A
#: SERP carries a dozen element types and most are not something a page can
#: win by being rewritten; these are.
WINNABLE_FEATURES = {
    "featured_snippet": "a featured snippet",
    "ai_overview": "an AI Overview",
    "people_also_ask": "a People Also Ask box",
    "faq": "an FAQ block",
    "video": "a video result",
    "images": "an image pack",
    "table": "a table",
}

#: How the work differs by feature, so "match the format" names a format.
FEATURE_SHAPE = {
    "featured_snippet": (
        "a 40 to 60 word answer directly under a heading that asks the query"
    ),
    "ai_overview": (
        "a short, quotable answer under a heading that asks the query, with "
        "the claim and its source in the same sentence"
    ),
    "people_also_ask": (
        "each related question as its own heading with a short answer under it"
    ),
    "faq": "a question-and-answer pair marked up as FAQPage",
    "video": "an embedded video with a transcript on the page",
    "images": "a captioned, descriptively named image near the answer",
    "table": "the comparison as a real table rather than prose",
}


#: A SERP feature is drawn from the results on page one. Prescribing the
#: format that wins one, to a page sitting at 47, is work that cannot pay:
#: the page is not in the set the feature is built from. SMA's "aeo agency"
#: is the case — the SERP carries an AI Overview, a People Also Ask box and
#: an image pack, and SMA holds no organic position on the page at all.
FEATURE_MAX_POSITION = 10.0


def t2_match_the_serp_format(page: PageCandidate) -> Prescription | None:
    """A feature on the query that the client does not hold."""
    if not page.serp_pulled or not page.top_query:
        return None
    # A navigational query's SERP is not a format to match.
    if page.top_query_is_navigational:
        return None
    if page.position is None or page.position > FEATURE_MAX_POSITION:
        return None
    winnable = [f for f in page.missing_serp_features if f in WINNABLE_FEATURES]
    if not winnable:
        return None

    feature = winnable[0]
    return Prescription(
        action_id="T-2",
        title=f"Add the format that wins {WINNABLE_FEATURES[feature]}",
        branch=Branch.TRAFFIC,
        target_url=page.url,
        term=page.top_query,
        score=page.impressions,
        effort_min=45,
        why=(
            f"“{page.top_query}” draws {page.impressions:.0f} impressions to "
            f"this page, which averages position {page.position:.1f}, and the "
            f"results carry {WINNABLE_FEATURES[feature]} the site does not "
            "hold. The page is on page one and competing for what is left "
            "after it."
        ),
        done_when=(
            f"The page carries {FEATURE_SHAPE[feature]}, answering the query "
            "in the words it is asked in."
        ),
        metric="Clicks against the curve's expectation",
        metric_key="page_clicks",
        evidence=(
            f"facts_serp_features: {', '.join(page.missing_serp_features)} "
            "present and not held",
            f"facts_gsc_pages: {page.impressions:.0f} impressions",
        ),
        check_after_days=30,
    )


TRAFFIC_ACTIONS: tuple[Callable[[PageCandidate], Prescription | None], ...] = (
    t1_rewrite_snippet,
    t2_match_the_serp_format,
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
        metric_key="page_lead_rate",
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
        metric_key="page_lead_rate",
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
        metric_key="page_lead_rate",
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
