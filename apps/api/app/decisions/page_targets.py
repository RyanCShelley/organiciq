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
