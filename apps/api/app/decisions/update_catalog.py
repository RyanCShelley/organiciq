"""What to do about a page that is losing ground.

The growth catalog asks what would win something new. This asks what is
being lost, which is a different question with a different allowance
behind it: refreshing existing content is retainer work a client buys
every month, and growth actions are deliberately outside it.

Same shape as `catalog.py` — plain functions taking a `PageCandidate` and
returning a `Prescription` or None, dispatched by `prescribe_page`, first
one to fire wins. The order of `UPDATE_ACTIONS` is therefore precedence,
and it runs most specific first: a page that fell out of the top three has
a sharper brief than one that is simply down, and both are better than
"refresh it".

Nothing here fires on impressions alone. ACCTek's
/managed-it-services-syracuse-ny lost 2,817 impressions over the weeks its
position improved from 32.7 to 21.5 — a SERP that changed shape, not a
page that decayed, and a refresh prescribed for it spends a month of a
client's allowance on a page that is winning.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from app.decisions.page_targets import PageCandidate
from app.decisions.slots import Prescription
from app.decisions.triage import Branch

#: Impressions a page must have drawn in the earlier window before its
#: decline means anything. Below this a halving is four impressions.
MIN_PRIOR_IMPRESSIONS = 100.0

#: How much of its demand a page has to have lost. A quarter is a real
#: fall and not a seasonal wobble; anything tighter and the queue fills
#: with pages that moved by noise.
MIN_DECLINE = 0.25

#: Positions worth winning back. A page that was averaging in the top
#: three and is not any more has lost the clicks that come with them,
#: which is the steepest part of the curve.
TOP_POSITIONS = 3.0

#: How far it has to have fallen as well as crossing the line. Boys
#: Electrical's /commercial went from 2.9 to 3.5 and was prescribed a
#: rewrite: an average position is a weighted mean over four weeks and it
#: breathes by half a place without anything happening.
MIN_POSITION_DROP = 2.0

#: How long before a refresh is judged. A position moves inside a month;
#: the impressions that follow it do not.
REFRESH_CHECK_DAYS = 56

#: Words below which a page is a stub, and "refresh it" is the wrong
#: instruction — there is nothing to refresh.
STUB_WORDS = 250


def _age(page: PageCandidate, today: date | None = None) -> str:
    """How long since the page said it was updated, in words.

    Silent where no source carried a date. A brief that says "last updated
    unknown" is noise; one that says nothing about the date is honest.
    """
    if page.content_updated_on is None:
        return ""
    months = ((today or date.today()) - page.content_updated_on).days // 30
    if months < 1:
        return " It was updated this month."
    if months == 1:
        return " It was last updated a month ago."
    if months < 24:
        return f" It was last updated {months} months ago."
    return f" It was last updated {months // 12} years ago."


#: Inbound editorial links below which a page is not being supported by
#: the rest of the site. Template links do not count — a menu link is not
#: a recommendation.
THIN_LINKS = 3

#: Words below which a page is short enough that "expand it" is part of
#: the job rather than a matter of taste.
THIN_WORDS = 600

#: How old the page's own date has to be before the brief names it. Some
#: platforms restamp every page on every deploy, so a recent date says
#: nothing and repeating it back makes the brief look broken.
STALE_MONTHS = 6


def _under_linked(page: PageCandidate) -> bool:
    return (
        page.inbound_editorial_links is not None
        and page.inbound_editorial_links < THIN_LINKS
    )


def _donor_steps(page: PageCandidate) -> list[str]:
    """One line per page that should link here, with the anchor to use.

    The donors come from the lever engine's own finder: pages that rank for
    the same query, earn at least twice this page's clicks on it, and have
    no body link to it. The sentence to put the link in is the one thing the
    data cannot choose, so the brief says so.
    """
    return [
        f"Link to it from {donor.url} using “{donor.anchor}” as the anchor — "
        "the query both pages already rank for. Put it in body copy, not the "
        "navigation."
        for donor in page.link_donors
    ]


def _steps(page: PageCandidate, term: str, today: date | None = None) -> tuple[str, ...]:
    """The job as a checklist, built only from facts about this page.

    A brief that says "refresh it" asks somebody to do the diagnosis
    again. Everything here is something the crawl or Search Console
    actually found, so each line is a thing to go and do — and a page
    with nothing wrong beyond its numbers gets a short list, honestly,
    rather than a padded one.
    """
    steps: list[str] = []

    if term and not _answers(page, term):
        steps.append(
            f"Add a heading that asks “{term}” in the words it is searched "
            "in, and answer it in the paragraph directly under it."
        )
    elif term:
        steps.append(
            f"Make the answer to “{term}” the first thing on the page, "
            "above anything else."
        )

    # Only worth naming the date when it is old enough to be the point.
    # On a site whose CMS restamps every page, "the copy has said last
    # week since it was last touched" is a sentence that reads as a
    # mistake, because it is one.
    stale_since = page.content_updated_on
    months_old = (
        ((today or date.today()) - stale_since).days // 30
        if stale_since is not None
        else 0
    )
    if stale_since is not None and months_old >= STALE_MONTHS:
        steps.append(
            f"Check every claim, figure and date in the copy — the page has "
            f"said {stale_since.isoformat()} for {months_old} months, and "
            "anything time-bound in it is that old."
        )
    else:
        steps.append("Check every claim, figure and date in the copy.")

    if page.broken_schema:
        steps.append(
            f"Fix the structured data: {', '.join(page.broken_schema)} is on "
            "the page and does not parse, which reads as no markup at all."
        )
    elif not page.has_schema:
        steps.append(
            "Add structured data for what this page is — there is none on it."
        )

    if page.faq_questions:
        count = len(page.faq_questions)
        steps.append(
            f"The page already answers {count} "
            f"question{'' if count == 1 else 's'}. Mark "
            f"{'it' if count == 1 else 'them'} up as FAQPage if not already."
        )

    if _under_linked(page) and page.link_donors:
        steps.extend(_donor_steps(page))
    elif _under_linked(page):
        steps.append(
            f"Link to it from related pages — only "
            f"{page.inbound_editorial_links} page"
            f"{'' if page.inbound_editorial_links == 1 else 's'} links to "
            "this one from body copy, which is not enough for the site to "
            "be pointing at it."
        )

    if page.word_count is not None and page.word_count < THIN_WORDS:
        steps.append(
            f"Expand it. At {page.word_count} words it is shorter than "
            "anything likely to be outranking it."
        )

    steps.append(
        "Republish with the modified date updated, so the change is "
        "something a crawler can see."
    )
    return tuple(steps)


def _is_decaying(page: PageCandidate) -> bool:
    """Lost a real share of real demand, and did not climb while doing it."""
    if page.prior_impressions < MIN_PRIOR_IMPRESSIONS:
        return False
    change = page.impressions_change
    if change is None or change > -MIN_DECLINE:
        return False
    # The ACCTek guard. A page whose ranking improved is not decaying
    # however its impressions moved — the SERP changed, not the page.
    return not page.held_or_improved_position


def _lost_query(page: PageCandidate) -> str:
    """The term the brief is about: the biggest loser, else the biggest.

    Navigational either way is no term at all. "Losing most on
    boyselectrical.com leadership team" sends somebody to rewrite a page
    for a query that was always going to be answered by the homepage.
    """
    if page.top_lost_query and not page.top_lost_query_is_navigational:
        return page.top_lost_query
    if page.top_query and not page.top_query_is_navigational:
        return page.top_query
    return ""


# ── U-2 ─────────────────────────────────────────────────────────────────


def u2_win_back_the_position(page: PageCandidate) -> Prescription | None:
    """It was in the top three on its main term and is not any more."""
    before = page.top_lost_query_prior_position
    after = page.top_lost_query_position
    term = page.top_lost_query
    if not term or before is None or before > TOP_POSITIONS:
        return None
    # A query that names the site is answered by whichever of your own
    # pages sits top, and no rewrite moves it. Boys Electrical's
    # /commercial was prescribed one for "boyselectrical.com leadership
    # team" — the same trap T-1 fell into on the same site.
    if page.top_lost_query_is_navigational:
        return None
    # Still there, or gone from the results entirely — the second is a
    # different problem and "win it back" is the wrong instruction.
    if after is None or after <= TOP_POSITIONS:
        return None
    # Crossing the line is not the same as losing the position. 2.9 to 3.5
    # is an average breathing, not a result that was overtaken.
    if after - before < MIN_POSITION_DROP:
        return None
    if page.prior_impressions < MIN_PRIOR_IMPRESSIONS:
        return None

    return Prescription(
        action_id="U-2",
        title="Win back the position this page lost",
        branch=Branch.VISIBILITY,
        target_url=page.url,
        term=term,
        score=page.impressions_lost,
        effort_min=90,
        why=(
            f"“{term}” was averaging position {before:.1f} on this page and "
            f"now averages {after:.1f}. The page has lost "
            f"{page.impressions_lost:.0f} impressions since the period "
            f"before.{_age(page)}"
        ),
        done_when=(
            f"The page answers “{term}” more completely than whatever now "
            "outranks it — read the results that passed it and cover what "
            "they cover that this does not."
        ),
        metric="Average position on the term",
        metric_key="term_position",
        evidence=(
            f"facts_gsc_query_pages: “{term}” {before:.1f} → {after:.1f}",
            f"facts_gsc_pages: {page.prior_impressions:.0f} → "
            f"{page.impressions:.0f} impressions",
        ),
        steps=_steps(page, term),
    )


# ── U-3 ─────────────────────────────────────────────────────────────────

#: A query that reads as a question. The same openers the crawler uses to
#: find a page's own questions, so "answered" and "asked" are judged by one
#: definition.
_QUESTION_OPENERS = (
    "what", "how", "why", "when", "where", "which", "who", "can", "does",
    "do", "is", "are", "should",
)


def _is_question(text: str) -> bool:
    words = (text or "").strip().lower().split()
    if not words:
        return False
    return text.strip().endswith("?") or words[0] in _QUESTION_OPENERS


def _answers(page: PageCandidate, term: str) -> bool:
    """Whether a heading or an FAQ entry already asks what the term asks.

    Matched on the content words, not the whole string: "how to track AI
    overviews" and "How do I track AI Overviews?" are the same question and
    a string compare says they are not.
    """
    wanted = {w for w in term.lower().split() if w not in _QUESTION_OPENERS and len(w) > 2}
    if not wanted:
        return True
    candidates = [str(q) for q in page.faq_questions]
    candidates += [str(s.get("heading") or "") for s in page.sections]
    for text in candidates:
        words = set(text.lower().replace("?", "").split())
        if wanted and wanted <= words:
            return True
    return False


def u3_answer_the_question_it_draws(page: PageCandidate) -> Prescription | None:
    """People arrive asking something the page never asks back."""
    term = _lost_query(page)
    if not term or not _is_question(term):
        return None
    if not _is_decaying(page):
        return None
    # Null sections means the crawl predates the capture, which is not the
    # same as a page with no headings. Nothing is prescribed on a guess.
    if not page.sections:
        return None
    if _answers(page, term):
        return None

    return Prescription(
        action_id="U-3",
        title="Answer the question this page draws",
        branch=Branch.VISIBILITY,
        target_url=page.url,
        term=term,
        score=page.impressions_lost,
        effort_min=45,
        why=(
            f"People reach this page asking “{term}”, and none of its "
            f"{len(page.sections)} headings asks that question. It has lost "
            f"{page.impressions_lost:.0f} impressions since the period "
            f"before.{_age(page)}"
        ),
        done_when=(
            f"A heading on the page asks “{term}” in the words it is "
            "searched in, with the answer in the paragraph directly under "
            "it."
        ),
        metric="Average position on the term",
        metric_key="term_position",
        evidence=(
            f"facts_gsc_query_pages: “{term}” is the biggest loser on this page",
            f"facts_crawl_page_snapshots: {len(page.sections)} headings, "
            f"{len(page.faq_questions)} questions answered",
        ),
        steps=_steps(page, term),
    )


# ── U-6 ─────────────────────────────────────────────────────────────────


def u6_fix_the_markup(page: PageCandidate) -> Prescription | None:
    """Structured data that is present and broken.

    Invalid markup is indistinguishable from absent to anything reading the
    page, and is invisible in every report we have — the schema summary
    counts blocks, and a block that did not parse still counts as one.
    """
    if not page.broken_schema:
        return None
    if page.impressions < MIN_PRIOR_IMPRESSIONS:
        return None

    broken = ", ".join(page.broken_schema)
    return Prescription(
        action_id="U-6",
        title="Fix the structured data on this page",
        branch=Branch.VISIBILITY,
        target_url=page.url,
        term=page.top_query,
        score=page.impressions,
        effort_min=30,
        why=(
            f"The page carries structured data that does not parse "
            f"({broken}), which to anything reading the page is the same as "
            f"carrying none. It draws {page.impressions:.0f} impressions."
        ),
        done_when=(
            "Every block on the page parses and validates, and the Rich "
            "Results test reports the type the page is meant to be."
        ),
        metric="Average position on the term",
        metric_key="term_position",
        evidence=(f"facts_crawl_page_schema: {broken} failed to parse",),
        steps=_steps(page, _lost_query(page)),
        check_after_days=REFRESH_CHECK_DAYS,
    )


# ── U-5 ─────────────────────────────────────────────────────────────────

#: Terms named in the brief. More than this and it reads as a list of
#: everything the site ranks for twice rather than a job.
MAX_CONTESTED_NAMED = 3


def u5_settle_which_page_owns_the_term(page: PageCandidate) -> Prescription | None:
    """Two of the site's own pages are splitting a query.

    Neither page is failing in itself, so no refresh fixes it: the engine
    is choosing between two answers and ranking neither well. The work is a
    decision — which page is the answer — and then making the other stop
    competing with it.
    """
    if not page.contested_terms:
        return None

    named = page.contested_terms[:MAX_CONTESTED_NAMED]
    lead = named[0]
    rivals = sorted({r.url for t in named for r in t.rivals})
    shared = sum(t.rival_impressions for t in page.contested_terms)

    def position(value: float | None) -> str:
        return f", averaging position {value:.1f}" if value is not None else ""

    steps: list[str] = []
    for t in named:
        steps.append(
            f"“{t.term}” ({t.total_impressions:.0f} impressions): this page draws "
            f"{t.own_impressions:.0f}{position(t.own_position)}; "
            + "; ".join(
                f"{r.url} draws {r.impressions:.0f}{position(r.position)}"
                for r in t.rivals
            )
            + "."
        )
    steps.append(
        f"Decide which page answers “{lead.term}”. If the two say the same thing, "
        "merge the weaker one into the stronger and redirect it. If they answer "
        "different questions, rewrite the weaker one's title and opening for the "
        "one it should be about, and stop it matching the term."
    )
    steps.append(
        f"Point every internal link that uses “{lead.term}” as its anchor at the page "
        "that owns it, so the site is not recommending both."
    )

    return Prescription(
        action_id="U-5",
        title="Settle which page owns this term",
        branch=Branch.VISIBILITY,
        target_url=page.url,
        term=lead.term,
        score=shared,
        effort_min=60,
        why=(
            f"“{lead.term}” is split across {len(lead.rivals) + 1} pages of this "
            f"site: this one holds {lead.own_impressions:.0f} of "
            f"{lead.total_impressions:.0f} impressions and "
            f"{', '.join(r.url for r in lead.rivals)} holds the rest. A search "
            "engine shown two near-answers from one site tends to rank neither well."
        ),
        done_when=(
            f"One page on the site answers “{lead.term}”; the other has been "
            "merged and redirected, or retargeted so it no longer draws it."
        ),
        metric="Average position on the term",
        metric_key="term_position",
        evidence=tuple(
            f"facts_gsc_query_pages: “{t.term}” — "
            + ", ".join(
                f"{u} {i:.0f}"
                for u, i in [(page.url, t.own_impressions)]
                + [(r.url, r.impressions) for r in t.rivals]
            )
            for t in named
        )
        + ((f"also shared with: {', '.join(rivals)}",) if len(rivals) > 1 else ()),
        steps=tuple(steps),
        check_after_days=REFRESH_CHECK_DAYS,
    )


# ── U-1 ─────────────────────────────────────────────────────────────────


def u1_refresh_the_page(page: PageCandidate) -> Prescription | None:
    """It is losing demand and nothing more specific explains it.

    Last in the order on purpose: every action above gives a sharper brief
    than "refresh it", and this one picks up what they leave.
    """
    if not _is_decaying(page):
        return None
    # A stub has nothing to refresh. Whatever is wrong with a 90-word page,
    # updating it is not the instruction.
    if page.word_count is not None and page.word_count < STUB_WORDS:
        return None

    term = _lost_query(page)
    about = f" It is losing most on “{term}”." if term else ""
    change = page.impressions_change or 0.0
    return Prescription(
        action_id="U-1",
        title="Refresh this page",
        branch=Branch.TRAFFIC,
        target_url=page.url,
        term=term or None,
        score=page.impressions_lost,
        effort_min=90,
        why=(
            f"Impressions are down {abs(change) * 100:.0f}% on the period "
            f"before, from {page.prior_impressions:.0f} to "
            f"{page.impressions:.0f}, and the ranking has not improved."
            f"{about}{_age(page)}"
        ),
        done_when=(
            "The page is current: claims and figures checked, anything "
            "dated replaced, and the opening answers what people are "
            "actually searching for. Republished with the date updated."
        ),
        metric="Impressions",
        metric_key="page_impressions",
        evidence=(
            f"facts_gsc_pages: {page.prior_impressions:.0f} → "
            f"{page.impressions:.0f} impressions",
            (
                f"position {page.prior_position:.1f} → {page.position:.1f}"
                if page.prior_position is not None and page.position is not None
                else "no position in one of the two periods"
            ),
        ),
        steps=_steps(page, term),
        check_after_days=REFRESH_CHECK_DAYS,
    )


# ── U-4 ─────────────────────────────────────────────────────────────────

#: The same band the lever engine's internal-linking finding uses. Above it
#: the page is already where links would take it; below it links are not
#: what is holding it back.
U4_MIN_POSITION = 4.0
U4_MAX_POSITION = 20.0


def u4_link_it_from_the_pages_that_should(page: PageCandidate) -> Prescription | None:
    """It draws demand, ranks within reach, and the site barely points at it.

    Last but one in the order on purpose: a page that is also decaying gets
    U-1 or sharper, and those briefs already carry these donors as steps.
    This picks up the pages nothing else is looking at because they have not
    lost anything — they have simply never been supported.
    """
    if not page.link_donors or not _under_linked(page):
        return None
    if page.impressions < MIN_PRIOR_IMPRESSIONS:
        return None
    if page.position is None or not (U4_MIN_POSITION <= page.position <= U4_MAX_POSITION):
        return None

    term = page.link_donors[0].anchor
    inbound = page.inbound_editorial_links or 0
    return Prescription(
        action_id="U-4",
        title="Link this page from the pages that should",
        branch=Branch.VISIBILITY,
        target_url=page.url,
        term=term,
        score=page.impressions,
        effort_min=30,
        why=(
            f"Only {inbound} page{'' if inbound == 1 else 's'} link to this one "
            f"from body copy, and it averages position {page.position:.1f} on "
            f"{page.impressions:.0f} impressions. "
            f"{len(page.link_donors)} stronger page"
            f"{'' if len(page.link_donors) == 1 else 's'} rank for the same "
            "query and do not link to it."
        ),
        done_when=(
            "Each page named below links here from body copy with the anchor "
            "given, and the crawl after publishing counts the new links."
        ),
        metric="Average position",
        metric_key="page_position",
        evidence=(
            f"facts_crawl_internal_links: {inbound} editorial links in",
            *(
                f"facts_gsc_query_pages: {d.url} earns {d.clicks:.0f} clicks on "
                f"“{d.anchor}”"
                for d in page.link_donors
            ),
        ),
        steps=tuple(_donor_steps(page))
        + (
            "Check the anchor reads naturally where you put it — the donor's "
            "body text is not stored, so the sentence is the one thing this "
            "brief cannot choose.",
        ),
        check_after_days=REFRESH_CHECK_DAYS,
    )


#: Most specific first — `prescribe_page` takes the first that fires, so
#: this order is what decides which brief a page gets.
UPDATE_ACTIONS: tuple[Callable[[PageCandidate], Prescription | None], ...] = (
    u2_win_back_the_position,
    u3_answer_the_question_it_draws,
    u6_fix_the_markup,
    u5_settle_which_page_owns_the_term,
    u1_refresh_the_page,
    u4_link_it_from_the_pages_that_should,
)


def rank_for_updates(pages: list[PageCandidate]) -> list[PageCandidate]:
    """Biggest loss first — impressions the site used to have and does not.

    Not a forecast of what a refresh would earn. Nothing can say that; this
    says what is already gone, which is measured.
    """
    return sorted(
        [
            p
            for p in pages
            if p.impressions_lost > 0
            or p.broken_schema
            or p.link_donors
            or p.contested_terms
        ],
        key=lambda p: (-p.impressions_lost, -p.impressions, p.url),
    )
