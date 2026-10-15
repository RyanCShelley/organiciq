"""What to do about a term the site has no page for.

Updates act on a page that exists. This acts on one that does not, which is
the other half of what a retainer's content allowance buys: a page written
for a term somebody is already paying to track.

The hard part is not the brief, it is being sure the page is missing. A
tracked term with no map entry and no suggestion looked like a gap on
ACCTek, and four of its six "gaps" — /structured-cabling, /vciso,
/remote-it-support, /it-strategy-services — were pages the site already
has. So absence is shown from the crawl: no indexable page carries the
term's words together in its title, URL or headings. A term that fails that
test is somebody's mapping job, not a page to write.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from app.decisions.slots import Prescription
from app.decisions.triage import Branch

#: Searches a month below which a page is not worth a slot of the
#: allowance. The same floor the AI-visibility rules already apply to
#: keywords.
MIN_VOLUME = 50.0

#: The share of a term's words one page must carry for the site to count as
#: already covering it. Set by reading Aquaman's seven candidate gaps against
#: its crawl by hand: with "every word" five of seven were topics a page
#: already answers ("is it safe to swim in cloudy pool water" beside
#: /blog/are-cloudy-pools-safe). A duplicate page is the costly error —
#: it competes with the one it repeats — so the line errs towards covered.
COVERED_SHARE = 0.6

#: How long before a new page is judged. A page published this month has
#: not been crawled, indexed and ranked by the next; position is the first
#: thing to move and it does so slowly.
CHECK_AFTER_DAYS = 90

#: Words that say nothing about what a page is about. Dropped before a term
#: is compared with a page, so "plumbers near me" and a page titled
#: "Plumbing Services" can be compared on "plumber"/"plumbing" alone.
_STOP = frozenset(
    "the of and for a an in to on at near me best top services service company "
    "companies how what is are do does vs with your".split()
)


#: Longest first, so "plumbers" loses "ers" and not just "s". Applied to
#: both sides of every comparison, so what matters is that the two agree
#: rather than that the result is a real word: "leaking" and "leak" meet at
#: "leak", and "leaking hot tub" is no longer a gap beside a post called
#: "find a hot tub leak quickly".
_SUFFIXES = ("ing", "ers", "er", "ed", "es", "s")


#: British spellings that differ from the American in a way no suffix rule
#: finds. Applied to both sides of every comparison, so a page written "fiber"
#: and a query typed "fibre" are the same word. Without it every such query
#: looked like demand for a page the site already has.
_SPELLING = {
    "fibre": "fiber", "centre": "center", "metre": "meter", "litre": "liter",
    "theatre": "theater", "calibre": "caliber", "colour": "color",
    "behaviour": "behavior", "favour": "favor", "neighbour": "neighbor",
    "labour": "labor", "honour": "honor", "grey": "gray", "tyre": "tire",
    "aluminium": "aluminum", "programme": "program", "cheque": "check",
}

_ISE = re.compile(r"^(.{3,})is(ation|ations|e|ed|es|ing)$")


def _spelling(word: str) -> str:
    if word in _SPELLING:
        return _SPELLING[word]
    match = _ISE.match(word)
    # optimisation -> optimization, organise -> organize. Applied the same on
    # both sides, so a word that merely ends this way ("promise" -> "promize")
    # still meets itself.
    return f"{match.group(1)}iz{match.group(2)}" if match else word


def _stem(word: str) -> str:
    word = _spelling(word)
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


#: A phrase that opens with one of these is a question, and its "it" is a
#: pronoun ("is it safe") rather than the industry ("it services").
_QUESTION_OPENERS = frozenset(
    "how what why when where which who is are can does do should will".split()
)


def content_words(text: str) -> frozenset[str]:
    """The words of a phrase that carry its meaning, lightly stemmed."""
    words = [w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if w]
    drop = _STOP | {"it"} if words and words[0] in _QUESTION_OPENERS else _STOP
    # A single letter ("i beam", "vitamin d") is not a word to match on; it
    # showed up as the one word no page carried.
    return frozenset(_stem(w) for w in words if w not in drop and not (len(w) == 1 and w.isalpha()))


@dataclass(frozen=True)
class NearPage:
    """The closest page the site has — somewhere to link the new one from."""

    url: str
    title: str | None
    shared: tuple[str, ...]


@dataclass(frozen=True)
class TermGap:
    """A tracked term with volume and no page that is about it."""

    term: str
    volume: float
    #: SE Ranking's 0-100 keyword difficulty. A gap is not scored without
    #: one: ranking by volume alone would put the term nobody can win first.
    difficulty: float | None
    intents: tuple[str, ...] = ()
    #: Smaller or larger variants of the same subject, folded into one page
    #: rather than prescribed three times.
    also_covers: tuple[tuple[str, float], ...] = ()
    nearest: tuple[NearPage, ...] = ()
    #: Features on the term's results, where a SERP has been pulled.
    serp_features: tuple[str, ...] = ()
    #: A person recorded this term as having no page yet. Stronger than the
    #: crawl test, because it is somebody's decision.
    recorded_no_page: bool = False
    #: How many indexable pages were searched, so the brief can say what the
    #: claim of absence rests on.
    pages_searched: int = 0
    #: Words of the term that appear in no page's title, URL or headings.
    #: "orlando" on a site that has never mentioned it is the cleanest
    #: evidence of a missing page there is.
    absent_words: tuple[str, ...] = ()
    #: Of the term's words, the largest share any one page carries.
    best_overlap: float = 0.0

    @property
    def weight(self) -> float:
        """What variants of one subject are ordered by when they are folded."""
        return self.volume

    @property
    def opportunity(self) -> float:
        """Searches a month the page could compete for.

        Volume discounted by difficulty. Not a forecast of visits — nothing
        can say what a page will earn — but it ranks a 480-search term at
        difficulty 12 above a 9,900-search term at 63 only where that is
        what the numbers say.
        """
        if self.difficulty is None:
            return 0.0
        return max(0.0, self.volume * (1.0 - min(self.difficulty, 100.0) / 100.0))


#: SE Ranking's one-letter intent codes, spelled out.
_INTENT = {
    "I": "informational",
    "N": "navigational",
    "C": "commercial",
    "T": "transactional",
    "L": "local",
}


def _intent(gap: TermGap) -> str:
    if not gap.intents:
        return ""
    named = " / ".join(_INTENT.get(i.strip().upper(), i) for i in gap.intents)
    return f" SE Ranking reads the intent as {named}."


def c1_write_the_page(gap: TermGap) -> Prescription | None:
    """A term people search, with no page on the site about it."""
    if gap.volume < MIN_VOLUME or gap.difficulty is None or gap.opportunity <= 0:
        return None

    if gap.recorded_no_page:
        basis = "It is recorded in the keyword map as having no page."
    elif gap.absent_words:
        words = ", ".join(f"“{w}”" for w in gap.absent_words)
        basis = (
            f"None of the {gap.pages_searched} indexable pages crawled mentions "
            f"{words} in its title, URL or headings."
        )
    else:
        basis = (
            f"Of the {gap.pages_searched} indexable pages crawled, the closest "
            f"carries {gap.best_overlap * 100:.0f}% of its words in its title, URL "
            "or headings."
        )

    steps: list[str] = [
        f"Write a page for “{gap.term}” — {gap.volume:,.0f} searches a month at "
        f"keyword difficulty {gap.difficulty:.0f}.{_intent(gap)} Put the term in "
        "the title, the URL and the first heading."
    ]
    if gap.also_covers:
        covered = ", ".join(f"“{t}” ({v:,.0f})" for t, v in gap.also_covers)
        steps.append(
            f"Cover the same subject under it rather than writing a page each: {covered}."
        )
    if gap.serp_features:
        steps.append(
            f"The results for this term carry {', '.join(gap.serp_features)}. Shape "
            "the page so a section answers in the form those results use."
        )
    if gap.nearest:
        steps.append(
            "Link the new page from the closest pages the site has: "
            + "; ".join(
                f"{p.url} (shares {', '.join(p.shared)})" for p in gap.nearest
            )
            + "."
        )
    steps.append(
        f"Add the page to the sitemap and map “{gap.term}” to its URL in the "
        "keyword map, so the engine tracks the one against the other."
    )

    return Prescription(
        action_id="C-1",
        title=f"Write the page for “{gap.term}”",
        branch=Branch.VISIBILITY,
        # There is no page yet. The empty string is the honest value: the
        # action's identity is the term.
        target_url="",
        term=gap.term,
        score=gap.opportunity,
        effort_min=240,
        why=(
            f"“{gap.term}” is tracked and draws {gap.volume:,.0f} searches a month, "
            f"and the site has no page about it. {basis}"
        ),
        done_when=(
            f"A page exists at its own URL, titled for “{gap.term}”, mapped to it "
            "in the keyword map and linked from the pages that sit closest to it."
        ),
        metric="Average position on the term",
        metric_key="term_position",
        evidence=(
            f"facts_ser_keyword_metrics: {gap.volume:,.0f} searches, difficulty "
            f"{gap.difficulty:.0f}",
            (
                "keyword_targets: recorded as having no page"
                if gap.recorded_no_page
                else f"facts_crawl_page_snapshots: no page of {gap.pages_searched} "
                + (
                    f"mentions {', '.join(gap.absent_words)}"
                    if gap.absent_words
                    else f"carries more than {gap.best_overlap * 100:.0f}% of the words"
                )
            ),
        ),
        steps=tuple(steps),
        check_after_days=CHECK_AFTER_DAYS,
    )


#: Impressions over the look-back below which a query is not demand worth a
#: page: about thirty a month. Set from what a month of Search Console shows
#: a small local site — a handful of queries a month is noise, not an audience
#: — and not from how many queries it lets through.
MIN_DEMAND_IMPRESSIONS = 90

#: A page already holding position 10 or better for the query is earning the
#: demand; writing a second one competes with it.
EARNING_POSITION = 10.0


@dataclass(frozen=True)
class DemandGap:
    """A query people send the site, which no page on it is about.

    The tracked-term gap starts from the terms somebody chose to watch, which
    on most clients is a short list. This starts from what Search Console says
    people searched before landing — or failing to land — on the site, so the
    demand it finds is demand nobody had to think of first.
    """

    term: str
    #: Impressions the site's results earned for the query over the look-back.
    #: Observed, and an undercount of the real search volume.
    impressions: float
    clicks: float
    #: Impression-weighted average position, across every page that showed.
    position: float | None
    #: The page that shows most for it — the page doing the job a new page
    #: should do properly.
    stand_in_url: str | None = None
    #: SE Ranking's figures, present only once the term has been priced.
    volume: float | None = None
    difficulty: float | None = None
    intents: tuple[str, ...] = ()
    also_covers: tuple[tuple[str, float], ...] = ()
    nearest: tuple[NearPage, ...] = ()
    pages_searched: int = 0
    absent_words: tuple[str, ...] = ()
    best_overlap: float = 0.0
    lookback_days: int = 90

    @property
    def weight(self) -> float:
        return self.impressions

    @property
    def priced(self) -> bool:
        return self.volume is not None and self.difficulty is not None

    @property
    def opportunity(self) -> float:
        """Searches a month the page could compete for, as for a tracked term.

        Zero until the term is priced: ranking by impressions alone would put
        the term nobody can win first, which is why a tracked gap is not
        scored without a difficulty either.
        """
        if not self.priced or self.volume < MIN_VOLUME:
            return 0.0
        return max(0.0, self.volume * (1.0 - min(self.difficulty, 100.0) / 100.0))


def c2_write_the_page_for_demand(gap: DemandGap) -> Prescription | None:
    """A query the site is already shown for, with no page about it."""
    if gap.opportunity <= 0:
        return None

    months = gap.lookback_days / 30
    if gap.absent_words:
        words = ", ".join(f"“{w}”" for w in gap.absent_words)
        basis = (
            f"None of the {gap.pages_searched} indexable pages crawled mentions "
            f"{words} in its title, URL or headings."
        )
    else:
        basis = (
            f"Of the {gap.pages_searched} indexable pages crawled, the closest "
            f"carries {gap.best_overlap * 100:.0f}% of its words in its title, URL "
            "or headings."
        )
    where = (
        f"; its average position is {gap.position:.0f}"
        if gap.position is not None
        else ""
    )
    stand_in = (
        f" The page Search Console shows for it is {gap.stand_in_url}, which is not "
        "about it."
        if gap.stand_in_url
        else ""
    )

    steps: list[str] = [
        f"Write a page for “{gap.term}” — {gap.volume:,.0f} searches a month at "
        f"keyword difficulty {gap.difficulty:.0f}. Put the term in the title, the "
        "URL and the first heading."
    ]
    if gap.also_covers:
        covered = ", ".join(f"“{t}” ({v:,.0f} impressions)" for t, v in gap.also_covers)
        steps.append(
            f"Cover the same subject under it rather than writing a page each: {covered}."
        )
    if gap.stand_in_url:
        steps.append(
            f"Link to the new page from {gap.stand_in_url}, which is where searchers "
            "land today, so the demand it already draws has somewhere better to go."
        )
    if gap.nearest:
        steps.append(
            "Also link it from the closest pages the site has: "
            + "; ".join(f"{p.url} (shares {', '.join(p.shared)})" for p in gap.nearest)
            + "."
        )
    steps.append(
        f"Add the page to the sitemap and map “{gap.term}” to its URL in the "
        "keyword map, so the engine tracks the one against the other."
    )

    return Prescription(
        action_id="C-2",
        title=f"Write the page for “{gap.term}”",
        branch=Branch.VISIBILITY,
        target_url="",
        term=gap.term,
        score=gap.opportunity,
        effort_min=240,
        why=(
            f"People searched “{gap.term}” and the site's results were shown "
            f"{gap.impressions:,.0f} times in {months:.0f} months{where}; SE Ranking "
            f"counts {gap.volume:,.0f} searches a month. Nobody is tracking it and "
            f"no page is about it. {basis}{stand_in}"
        ),
        done_when=(
            f"A page exists at its own URL, titled for “{gap.term}”, mapped to it "
            "in the keyword map and linked from the pages that sit closest to it."
        ),
        metric="Average position on the term",
        metric_key="term_position",
        evidence=(
            f"facts_gsc_query_pages: {gap.impressions:,.0f} impressions, "
            f"{gap.clicks:,.0f} clicks over {gap.lookback_days} days",
            f"facts_ser_keyword_metrics: {gap.volume:,.0f} searches, difficulty "
            f"{gap.difficulty:.0f}",
            f"facts_crawl_page_snapshots: no page of {gap.pages_searched} is about it",
        ),
        steps=tuple(steps),
        check_after_days=CHECK_AFTER_DAYS,
    )


def prescribe_demand(gap: DemandGap) -> Prescription | None:
    return c2_write_the_page_for_demand(gap)


def rank_demand(gaps: list[DemandGap]) -> list[DemandGap]:
    return sorted(
        [g for g in gaps if g.opportunity > 0], key=lambda g: (-g.opportunity, g.term)
    )


CONTENT_ACTIONS: tuple[Callable[[TermGap], Prescription | None], ...] = (
    c1_write_the_page,
)


def prescribe_term(gap: TermGap) -> Prescription | None:
    for action in CONTENT_ACTIONS:
        found = action(gap)
        if found is not None:
            return found
    return None


def rank_for_content(gaps: list[TermGap]) -> list[TermGap]:
    """Biggest winnable prize first."""
    return sorted(
        [g for g in gaps if g.opportunity > 0], key=lambda g: (-g.opportunity, g.term)
    )


def fold_variants(gaps: list) -> list:
    """One page per subject: a term whose words contain, or are contained
    by, a bigger term's words rides along with it.

    "commercial pressure washing" and "pressure washing" are one page. The
    biggest term by volume leads and the rest are named under it, so the
    brief says which variants the page has to cover and nobody is given
    three slots for one subject.
    """
    ordered = sorted(gaps, key=lambda g: (-g.weight, g.term))
    leads: list = []
    folded: dict[str, list[tuple[str, float]]] = {}
    for gap in ordered:
        words = content_words(gap.term)
        home = next(
            (
                lead
                for lead in leads
                if words and (words <= content_words(lead.term) or content_words(lead.term) <= words)
            ),
            None,
        )
        if home is None:
            leads.append(gap)
            folded[gap.term] = list(gap.also_covers)
        else:
            folded[home.term].append((gap.term, gap.weight))
    return [replace(lead, also_covers=tuple(folded[lead.term])) for lead in leads]
