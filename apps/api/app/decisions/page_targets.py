"""Pages as candidates, for the Traffic and Leads branches.

Visibility asks about a term on a page: Decision 2 ranks `keyword_targets`
and the action names the term. Traffic and Leads ask about the page itself —
a page that earns fewer clicks than its position should, a page people land on
and leave, a page with nowhere to go next. The unit is different, so the
pipeline is, rather than bending a keyword candidate into a shape it is not.

Both branches rank on a **measured** quantity: traffic on clicks the page did
not get against the curve's own expectation, leads on the sessions already
landing there. Neither is a forecast. Nothing here estimates what an action
would earn, because nothing can.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class LinkDonor:
    """A page that should link to the candidate, and what to say when it does."""

    url: str
    #: A query both pages already rank for, so the anchor is one the search
    #: engine has already tied to both.
    anchor: str
    clicks: float = 0.0
    refdomains: int = 0


#: Impressions a query must draw across all the site's pages before a split
#: between two of them is worth a month's work. Below it, a "split" is a
#: handful of stray impressions.
CONTESTED_MIN_IMPRESSIONS = 100.0

#: The share of a query's impressions the second page must hold. Not a
#: tuned number: at 20% SMA has 4 contested queries and ACCTek 4, at 30% 2
#: and 3 — the set barely moves, so the line is not what decides it.
CONTESTED_MIN_RIVAL_SHARE = 0.3


@dataclass(frozen=True)
class Rival:
    url: str
    impressions: float
    position: float | None = None


@dataclass(frozen=True)
class ContestedTerm:
    """A query two or more of the site's own pages are both drawing."""

    term: str
    #: Impressions across every page of the site, and the candidate's share.
    total_impressions: float
    own_impressions: float
    own_position: float | None
    rivals: tuple[Rival, ...]

    @property
    def rival_impressions(self) -> float:
        return sum(r.impressions for r in self.rivals)


@dataclass(frozen=True)
class PageCandidate:
    """One page, with what the Traffic and Leads triggers need to judge it."""

    url: str
    title: str | None = None
    description: str | None = None

    # ── Traffic ──
    impressions: float = 0.0
    clicks: float = 0.0
    #: GSC's average position over the window. None where the page had no
    #: impressions at all.
    position: float | None = None
    #: What the measured CTR curve says a page at this position earns.
    expected_clicks: float | None = None
    #: The query drawing the most impressions, so the action can name what
    #: the snippet has to answer rather than saying "the term".
    top_query: str | None = None
    #: Whether that query names the site itself. Boys Electrical's /about-us
    #: sat at position 1.9 on 3,872 impressions with 4 clicks — 418 "missed"
    #: by the curve — for the query "boyselectrical.com leadership team". The
    #: clicks went to the homepage at position 1. On a query that names the
    #: site, CTR is decided by which of your own results sits top, and no
    #: title rewrite moves it.
    top_query_is_navigational: bool = False

    # ── Engagement ──
    sessions: float = 0.0
    engaged_sessions: float | None = None
    #: The site's own median engagement rate, so "low" is relative to this
    #: site and not to a number somebody picked.
    site_median_engagement: float | None = None

    # ── Leads ──
    #: Confirmed funnel stage. None means nobody has said, and no lead action
    #: fires on a guess.
    stage: str | None = None
    #: In-content, non-template links from this page to a declared conversion
    #: page, by that page's stage.
    linked_offer_stages: frozenset[str] = frozenset()
    #: Conversion pages whose stage suits this page's reader, best first.
    matched_offers: tuple[str, ...] = ()
    #: The crawl's count of forms and calls to action. None where the crawl
    #: predates the capture — distinct from a page with none.
    conversion_elements: int | None = None
    #: Features on this page's top query that the client does not hold, in
    #: DataForSEO's spelling. Empty where no SERP has been pulled — which is
    #: not the same as a SERP with nothing on it, so T-2 needs `serp_pulled`
    #: before it will speak.
    missing_serp_features: tuple[str, ...] = ()
    serp_pulled: bool = False
    #: This page is itself a declared conversion page. It is the destination,
    #: so "route the reader onward" has nowhere left to send them.
    is_conversion_page: bool = False

    # ── The period before ──
    #
    # The same three figures over the 28 days before the window above. An
    # update is prescribed for a page that is losing something, and one
    # period cannot say that. `prior_position` is None where the page drew
    # no impressions then, which is also how `has_prior` tells a decaying
    # page from one that did not exist yet.
    prior_impressions: float = 0.0
    prior_clicks: float = 0.0
    prior_position: float | None = None
    #: The query whose impressions fell most on this page, so the brief can
    #: name what was lost rather than saying the page is down.
    top_lost_query: str | None = None
    #: Whether that query names the site itself. A brand query's position
    #: is decided by which of your own results sits top, and no rewrite
    #: moves it — the same trap T-1 fell into on Boys Electrical.
    top_lost_query_is_navigational: bool = False
    #: That query's position then and now. Null where it drew nothing in one
    #: of the two windows.
    top_lost_query_prior_position: float | None = None
    top_lost_query_position: float | None = None

    # ── The page itself ──
    #: When the page was last updated, and which source said so. Null where
    #: the crawl found no date, which is not the same as a page never
    #: updated — the column says "unknown" and no rule guesses.
    content_updated_on: date | None = None
    content_updated_source: str | None = None
    word_count: int | None = None
    #: In-content, non-template links pointing at this page.
    inbound_editorial_links: int | None = None
    #: Section headings in document order, and the questions the page
    #: already answers. Null where the crawl predates the capture.
    sections: tuple[dict, ...] = ()
    faq_questions: tuple[str, ...] = ()
    #: Schema blocks on the page that failed to parse, by type where known.
    #: Invalid markup is indistinguishable from absent to every consumer.
    broken_schema: tuple[str, ...] = ()
    has_schema: bool = False
    #: Pages that share a query with this one, earn at least twice its
    #: clicks on it, and do not link to it from body copy. Best donor first.
    #: Only searched for under-linked pages, so empty means "not looked for"
    #: as often as "none found" — U-4 needs the under-linked test as well.
    link_donors: tuple[LinkDonor, ...] = ()
    #: Non-brand queries this page draws the most of while another page of
    #: the same site also draws a real share. Biggest first.
    contested_terms: tuple[ContestedTerm, ...] = ()

    @property
    def missed_clicks(self) -> float | None:
        """Clicks the curve expected and the page did not get.

        None where there is nothing to compare against, rather than zero: a
        page with no position has not "missed nothing".
        """
        if self.expected_clicks is None:
            return None
        return max(0.0, self.expected_clicks - self.clicks)

    @property
    def engagement_rate(self) -> float | None:
        if self.engaged_sessions is None or not self.sessions:
            return None
        return self.engaged_sessions / self.sessions

    @property
    def routes_onward(self) -> bool:
        return bool(self.linked_offer_stages)

    @property
    def has_prior(self) -> bool:
        """Whether this page drew anything in the period before.

        A page published last month has no earlier figures, and a page with
        nothing to compare against is not a page that lost something.
        """
        return self.prior_impressions > 0

    @property
    def impressions_lost(self) -> float:
        """Impressions the page used to draw and no longer does."""
        if not self.has_prior:
            return 0.0
        return max(0.0, self.prior_impressions - self.impressions)

    @property
    def impressions_change(self) -> float | None:
        """As a share of what it drew before. -0.25 is a quarter gone."""
        if not self.has_prior:
            return None
        return (self.impressions - self.prior_impressions) / self.prior_impressions

    @property
    def position_change(self) -> float | None:
        """Positive means it moved down the page. None where either is absent."""
        if self.position is None or self.prior_position is None:
            return None
        return self.position - self.prior_position

    @property
    def held_or_improved_position(self) -> bool:
        """Whether the ranking is no worse than it was.

        ACCTek's /managed-it-services-syracuse-ny lost 7,524 impressions
        and *improved* from 32.7 to 21.5 over the same weeks. Impressions
        alone would call that a decaying page; it is a SERP that changed
        shape. Nothing is prescribed as decay unless the ranking slipped.
        """
        change = self.position_change
        return change is not None and change <= 0


def rank_for_traffic(pages: list[PageCandidate]) -> list[PageCandidate]:
    """Busiest shortfall first, by clicks the page did not get."""
    scored = [p for p in pages if (p.missed_clicks or 0) > 0 or p.sessions > 0]
    return sorted(
        scored,
        key=lambda p: (-(p.missed_clicks or 0.0), -p.sessions, p.url),
    )


def rank_for_leads(pages: list[PageCandidate]) -> list[PageCandidate]:
    """Most sessions first — the traffic a lead action is spending."""
    return sorted(
        [p for p in pages if p.sessions > 0],
        key=lambda p: (-p.sessions, p.url),
    )
