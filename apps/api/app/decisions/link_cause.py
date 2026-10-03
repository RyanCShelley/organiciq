"""Which page should link to which, with what anchor. Playbook 6.

The old finding said "add internal links from mapped authoritative pages",
which names no page, no anchor and no place to put one.

The playbook's donor finder has four steps. Vector similarity is the first
and there are no embeddings, so shared Search Console queries stand in —
the same evidence, arrived at differently: two pages ranking for one query
are about one subject. The fourth step, finding a sentence in the donor
that already mentions the target's term, needs the donor's body text,
which is not stored. So the anchor is named and placing it is the one part
left to a person.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.decisions.prescription import Prescription, Step


@dataclass(frozen=True)
class Donor:
    url: str
    anchor: str
    clicks: float
    refdomains: int = 0


@dataclass(frozen=True)
class LinkSignals:
    page_url: str
    position: float
    inbound_links: int
    floor: int
    donors: list[Donor] = field(default_factory=list)
    recoverable_clicks: float = 0.0


def classify_link_gap(signals: LinkSignals) -> Prescription:
    evidence = {
        "inbound_editorial_links": signals.inbound_links,
        "link_floor": signals.floor,
        "average_position": round(signals.position, 1),
        "donors_found": len(signals.donors),
    }

    if not signals.donors:
        # No page shares a subject and has anything to lend. Saying "add
        # internal links" anyway would be the old finding again.
        return Prescription(
            cause="undetermined",
            evidence=evidence,
            steps=[
                Step(
                    "Decide which existing page should link to this one, or write the "
                    "page that would",
                    target=signals.page_url,
                    detail=f"It has {signals.inbound_links} editorial links against a "
                    f"floor of {signals.floor}, and no page on the site both shares a "
                    "search query with it and has the authority to lend. That gap is "
                    "usually missing coverage rather than missing links.",
                    human=True,
                ),
            ],
            expected_impact=f"about {signals.recoverable_clicks:,.0f} clicks a period",
            verify_metric="average_position",
            verify_after_days=28,
        )

    steps = [
        Step(
            f"Link to this page from {donor.url}",
            target=donor.url,
            detail=f"Use “{donor.anchor}” as the anchor — it is the query "
            f"both pages already rank for. The donor draws {donor.clicks:,.0f} clicks"
            + (
                f" and has {donor.refdomains} referring domains"
                if donor.refdomains
                else ""
            )
            + ". Place it in the body, not the navigation: a site-wide link says "
            "nothing about this page in particular.",
        )
        for donor in signals.donors
    ]
    steps.append(
        Step(
            "Check the anchor reads naturally where you put it",
            target=signals.page_url,
            detail="The donor's body text is not stored, so the sentence to put the "
            "link in is the one part of this our data cannot choose.",
            human=True,
        )
    )

    return Prescription(
        cause="undetermined",
        evidence={
            **evidence,
            "donors": [
                {"url": d.url, "anchor": d.anchor, "clicks": round(d.clicks)}
                for d in signals.donors
            ],
        },
        steps=steps,
        expected_impact=f"about {signals.recoverable_clicks:,.0f} clicks a period",
        verify_metric="average_position",
        verify_after_days=28,
    )
