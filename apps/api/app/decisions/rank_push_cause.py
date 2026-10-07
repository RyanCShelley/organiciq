"""Pages with demand sitting just below where the clicks are.

Capping CTR work at the top five leaves a band the engine had nothing to
say about. Positions six to ten are where it matters most: the measured
curve pays 1.08% at five and 0.73% at six, so a page here has done the
hard part — Google shows it for a term people search — and earns almost
nothing for it. Moving it three places is worth more than any listing
rewrite could have been.

So the instruction is rank, not the listing. What actually moves rank and
we can see: links the site is not giving it, and whether anything is
holding it back technically. What we cannot see is what the pages above it
cover, which stays a person's job and is named as one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.decisions.prescription import Prescription, Step


@dataclass(frozen=True)
class RankPushDonor:
    url: str
    anchor: str
    clicks: float


@dataclass(frozen=True)
class RankPushSignals:
    page_url: str
    top_query: str | None
    position: float
    impressions: float
    clicks: float
    #: Clicks the page would earn at the top of the band, from the curve.
    clicks_at_target: float
    inbound_links: int | None = None
    link_floor: int | None = None
    #: How many donor links one action may ask for. The cap is what makes
    #: the hour true.
    donor_cap: int = 5
    donors: list[RankPushDonor] = field(default_factory=list)
    word_count: int | None = None


def classify_rank_push(signals: RankPushSignals) -> Prescription | None:
    """The links to add, or None when there is no hour-sized move.

    With the content comparison removed, a page that already has its links
    and shares no query with a donor leaves nothing that fits an hour.
    Saying so is better than keeping a card with no step on it.
    """
    gain = max(0.0, signals.clicks_at_target - signals.clicks)
    evidence = {
        "top_query": signals.top_query,
        "average_position": round(signals.position, 1),
        "impressions": round(signals.impressions),
        "clicks": round(signals.clicks),
        "clicks_at_top_five": round(signals.clicks_at_target),
        "inbound_editorial_links": signals.inbound_links,
        "word_count": signals.word_count,
    }

    steps: list[Step] = []

    # Links first: it is the only lever here our own data can both find and
    # name, and it is the cheapest of the three.
    for donor in signals.donors[: signals.donor_cap]:
        steps.append(
            Step(
                f"Link to this page from {donor.url}",
                target=donor.url,
                detail=f"Use “{donor.anchor}” as the anchor — the query both "
                f"pages rank for. The donor draws {donor.clicks:,.0f} clicks and is not "
                "passing any of that authority on.",
            )
        )
    if not signals.donors and signals.inbound_links is not None and signals.link_floor:
        if signals.inbound_links < signals.link_floor:
            steps.append(
                Step(
                    "Link to this page from the section it belongs to",
                    target=signals.page_url,
                    detail=f"{signals.inbound_links} editorial links against a floor of "
                    f"{signals.link_floor}. No page shares a query with it, so the link "
                    "has to come from the hub rather than a sibling.",
                )
            )

    # The "cover what the top five results cover" step is gone. It is a
    # content project measured in days, and a growth action is an hour.
    # Leaving it on the card made the action look like one thing and cost
    # another, which is how an hour's budget gets spent on a week's work.

    if not steps:
        return None

    return Prescription(
        cause="rank_push",
        evidence=evidence,
        steps=steps,
        expected_impact=f"about {gain:,.0f} clicks a period at position five",
        verify_metric="average_position",
        verify_after_days=56,
    )
