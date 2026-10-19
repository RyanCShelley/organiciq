"""Evidence-based growth actions with stable rule identities.

Automatic actions use the active catalogs below. Legacy rule functions remain
available for historical records and explicit evaluation; their existence does
not make them automatic recommendations. Missing exact wording or optional
entity properties alone does not establish an actionable gap.
"""

from __future__ import annotations

import re
import unicodedata

from dataclasses import dataclass
from typing import Callable

from app.decisions.page_targets import PageCandidate, LinkDonor
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
    level: int = 2

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
    #: The crawl read this page. False where no snapshot matched the target
    #: URL, in which case the title, description and headings are not "empty",
    #: they are unknown, and nothing is prescribed from them.
    crawled: bool = True
    #: The crawl captured the page's headings. A crawl that predates the
    #: capture leaves `headings` empty, which would read as a page with no
    #: heading at all.
    headings_known: bool = True
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
    link_donors: tuple[LinkDonor, ...] = ()

    @property
    def readable(self) -> bool:
        """Whether the crawl actually read this page as served.

        Headings, FAQ questions, schema and link counts are all recorded only
        for a page fetched as a 2xx and parsed. Where that did not happen they
        arrive empty or zero, and a rule that reads empty as "the page has
        none" prescribes work on a page nobody looked at.
        """
        return self.crawled and self.headings_known


@dataclass(frozen=True)
class SkippedAction:
    action_id: str
    reason: str


#: Why an action cannot fire, named rather than silent.
NO_SERP_FEATURES = (
    "needs the full SERP feature list for the query, which is not pulled — "
    "only features the client already holds are stored"
)


def _mentions(term: str, text: str | None) -> bool:
    """Whether the text uses the term, phrase-aware.

    A bag of words matches "agency seo local" to "local seo agency", which is
    how a page that never says the phrase was reported as already optimised
    for it.
    """
    if not text:
        return False
    def words(value):
        return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value).casefold())
    needle, haystack = words(term), words(text)
    return bool(needle) and any(haystack[i:i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1))


# ── Visibility ──────────────────────────────────────────────────────────────


def v1_term_in_high_value_spots(
    target: ScoredCandidate, page: PageFacts
) -> Prescription | None:
    """A primary term missing from the title or from every heading.

    Primary only. A page has one title and it belongs to the term the page
    is *for*: telling somebody to put a secondary term in it is telling them
    to take the primary term out, and the engine would then find that
    missing next month and ask for it back.

    It asks only for what it can read and what it tells the reader to do. The
    meta description is not one of them: it is not a ranking input and Google
    rewrites it, so a page whose title and heading carry the term was being told
    its term was missing because of a snippet. And a page the crawl did not read,
    or read before headings were captured, is unknown rather than empty.
    """
    if target.candidate.term_role != "primary":
        return None
    if not page.crawled:
        return None
    term = target.candidate.keyword
    in_title = _mentions(term, page.title)
    in_headings = (not page.headings_known) or any(
        _mentions(term, h) for h in page.headings
    )
    if in_title and in_headings:
        return None

    missing = [
        label
        for label, present in (("the title", in_title), ("any heading", in_headings))
        if not present
    ]
    missing_text = " or ".join(missing)
    where = " and ".join(
        place
        for place, present in (("the title", in_title), ("a heading", in_headings))
        if not present
    )
    where_done = " and ".join(
        place
        for place, present in (
            ("the title tag", in_title),
            ("one H2", in_headings),
        )
        if not present
    )
    return Prescription(
        action_id="V-1",
        title=f"Put “{term}” in {where}",
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
            f"“{term}” appears in {where_done}, reading as a sentence rather "
            "than an insertion."
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
    if not page.crawled or not page.headings_known:
        return None
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
    if not page.readable:
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
    if not page.readable:
        return None
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
    if not page.readable or not page.link_donors:
        return None
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
        done_when="The named donor links are live in relevant body passages and point to the target page.",
        steps=tuple(f'On {donor.url}, add an in-content link to {page.url} where the passage discusses “{donor.anchor}”. Use a natural anchor and confirm the passage is relevant before publishing.'
                    for donor in page.link_donors),
        metric="Term position",
        metric_key="term_position",
        evidence=(
            f"facts_crawl_internal_links: {page.inbound_editorial_links} editorial "
            f"inbound, site median {page.site_median_links:.0f}",
            *(f"Shared query: {d.anchor}; donor: {d.url}; donor clicks: {d.clicks:g}. No existing editorial link was observed." for d in page.link_donors),
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
    if not page.readable or page.has_faq_schema or not page.has_faq_section:
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
            "and no FAQPage markup. Verify the visible question-and-answer pairs "
            "before adding matching structured data. This does not guarantee "
            "a rich result, ranking improvement or AI citation."
        ),
        done_when=(
            "FAQPage markup lists every question in that section with the "
            "answer the page already gives, word for word, and nothing that "
            "is not on the page."
        ),
        metric="Validated FAQ markup matching the visible questions and answers",
        metric_key="decision",
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
    # A heading's answer includes its nested subheadings. Checking only the
    # opening paragraph made an H1 look unstructured even when its H2s
    # already supplied the relevant lists or tables.
    for index, section in enumerate(page.sections):
        if section not in matching:
            continue
        scope = [section]
        for child in page.sections[index + 1:]:
            if child.level <= section.level:
                break
            scope.append(child)
        if any(part.extractable for part in scope):
            return None

    feature = sorted(lifted)[0]
    return Prescription(
        action_id="V-5",
        title=f"Review the answer format for “{term}”",
        branch=Branch.VISIBILITY,
        target_url=page.url,
        term=term,
        score=target.score,
        effort_min=45,
        why=(
            f"The results for “{term}” carry {EXTRACTIVE_FEATURES[feature]}, "
            "which makes this section worth reviewing. The crawl detected "
            "no table, list or stat block under the matching heading. "
            "A direct prose answer may already be sufficient; verify the gap first."
        ),
        done_when=(
            "Review whether the existing prose already answers the question. "
            "Record no change if it does. Otherwise name the verified answer "
            "gap, select a suitable format and supporting facts, and publish "
            "only the justified change."
        ),
        metric="Documented answer-format review and selected next step",
        metric_key="decision",
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


#: Active automatic visibility actions, in priority order.
VISIBILITY_ACTIONS: tuple[Callable[[ScoredCandidate, PageFacts], Prescription | None], ...] = (
    v6_rehoming,
    # V-1 and V-8 are legacy: exact-phrase absence alone is not a content gap.
    # A missing exact-match secondary heading alone does not prove a content gap.
    # Missing question headings do not establish missing answers.
    # v2_answer_block remains available for historical records only.
    # Before the rest: the answers are already written, so this is fifteen
    # minutes of markup against a page rewrite. Cheapest first where the
    # cheap thing is also the right thing.
    v7_mark_up_the_faq,
    # Before V-3 and V-4: when an engine is visibly lifting an answer,
    # giving it something to lift beats marking up or linking to a page it
    # cannot quote.
    v5_add_an_extractable_structure,
    # Optional about/mentions absence alone does not justify an automatic task.
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
MIN_SESSIONS_FOR_ENGAGEMENT = 150.0


def t1_rewrite_snippet(page: PageCandidate) -> Prescription | None:
    """Top-three page earning fewer clicks than its position should."""
    missed = page.missed_clicks
    if (
        missed is None
        or page.position is None
        or page.position > SNIPPET_MAX_POSITION
        or page.impressions < MIN_IMPRESSIONS
        or missed < 5
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
            f"impressions. A reference CTR scenario estimates "
            f"{page.expected_clicks:.0f}. At the top of the page one, what is "
            "worth reviewing is query intent, the results layout and the snippet. "
            "The benchmark is an estimate and does not establish the cause."
        ),
        done_when=(
            "The title is 60 characters or fewer, carries the term and a "
            "reason to click that the page delivers, and the old version is "
            "logged so the check has something to compare."
        ),
        metric="Observed Search Console clicks after the change",
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
        title="Review engagement and visitor intent",
        branch=Branch.TRAFFIC,
        target_url=page.url,
        term=page.top_query,
        score=page.sessions * (page.site_median_engagement - rate),
        effort_min=60,
        why=(
            f"{page.sessions:.0f} sessions landed here and "
            f"{rate * 100:.0f}% engaged, against a site median of "
            f"{page.site_median_engagement * 100:.0f}%. The page is winning "
            "visits with lower recorded engagement. Review the visitor intent "
            "and opening before deciding whether a rewrite is the right intervention."
        ),
        done_when=(
            "Compare channel and device mix, visitor intent and lead outcomes. "
            "Record whether the engagement gap needs a page change, a tracking "
            "fix or no intervention. Rewrite the opening only if a content "
            "mismatch is verified."
        ),
        metric="Documented cause and selected next step",
        metric_key="decision",
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
        metric="Observed Search Console clicks after the change",
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


# A prioritization floor, not a claim of statistical significance. Visibility
# work on strategic low-traffic pages remains available independently.
MIN_SESSIONS_FOR_LEAD_ACTION = 50


def _lead_page_eligible(page: PageCandidate) -> bool:
    from app.services.page_eligibility import classify_page_url
    return (page.crawl_readable and page.sessions >= MIN_SESSIONS_FOR_LEAD_ACTION
            and classify_page_url(page.url).eligible_for_growth_action)


def l1_route_to_the_next_step(page: PageCandidate) -> Prescription | None:
    """A page people land on with no in-content way forward."""
    if not _lead_page_eligible(page) or page.stage is None or page.stage == "bofu" or page.routes_onward:
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
            "qualifying in-content link detected to a declared conversion page. "
            "This is crawl evidence, not measured visitor progression. Verify "
            "the page and destination before changing the route."
        ),
        done_when=(
            f"An in-content link to {page.matched_offers[0]}, with a sentence "
            "saying what the reader gets by following it, placed where the "
            "page has finished answering what they came for."
        ),
        metric="Page-local lead events per landing session (not journey attribution)",
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
    if not _lead_page_eligible(page) or page.stage is None or page.conversion_elements is None:
        return None
    if page.conversion_elements > 0:
        return None
    if page.stage == "tofu" and not page.matched_offers:
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
        metric="Page-local lead events per landing session (not journey attribution)",
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
    if not _lead_page_eligible(page) or page.stage is None or not page.routes_onward or not page.matched_offers:
        return None
    if page.is_conversion_page:
        return None
    if "generic" in page.linked_offer_stages:
        return None  # Unknown intent is not proof that an existing route is wrong.
    fits = set(STAGE_FIT.get(page.stage, ()))
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
        metric="Page-local lead events per landing session (not journey attribution)",
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
