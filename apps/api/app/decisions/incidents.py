"""Things that are wrong with the site, as opposed to things to grow.

Per rule: an incident does not take a slot and does not change the constraint.
A site that stopped recording leads has a broken tag, not a conversion
problem, and spending a growth slot on it would be answering the wrong
question — while saying nothing would let the engine keep prescribing
optimisation on a page nobody can convert on.

Three of them, each from a fact the warehouse already holds:

  * leads stopped — zero lead events for a fortnight, after a history of them
  * pages vanished — a fifth of the indexable pages gone since the last crawl
  * the markup names somebody else — Organization schema carrying a brand
    that is not this client's

All three are *site-wide*. A single page losing its schema is on-page work
and belongs in the retainer; the whole site naming the wrong company is an
incident.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Incident:
    uid: str
    title: str
    #: What it covers. Always site-wide here, named so the card can say so.
    scope: str
    detail: str
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "incident_uid": self.uid,
            "title": self.title,
            "scope": self.scope,
            "detail": self.detail,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class IncidentSignals:
    """What the three checks read. None means the check cannot run."""

    #: Days since the last lead event, where the client has ever had one.
    days_since_last_lead: int | None = None
    #: Lead events in the 90 days before that, so a client who has never had
    #: one is not reported as having stopped.
    leads_in_prior_window: float = 0.0

    indexable_now: int | None = None
    indexable_before: int | None = None
    crawl_before_date: str | None = None

    #: Organization names found in the site's markup that are not the
    #: client's, with how many pages carry each.
    foreign_brands: tuple[tuple[str, int], ...] = ()
    pages_with_organization: int = 0


#: A fortnight of silence after a history of leads. Shorter catches a quiet
#: fortnight; longer and half the month is gone before anybody is told.
LEAD_SILENCE_DAYS = 14

#: The spec's figure. A fifth of the indexable pages is a deployment, not
#: drift.
PAGE_DROP_SHARE = 0.20


def check(signals: IncidentSignals, *, month: str, slug: str) -> list[Incident]:
    found: list[Incident] = []

    if (
        signals.days_since_last_lead is not None
        and signals.days_since_last_lead >= LEAD_SILENCE_DAYS
        and signals.leads_in_prior_window > 0
    ):
        found.append(
            Incident(
                uid=f"{slug}-{month}-leads-stopped",
                title="No lead has been recorded for two weeks",
                scope="Site-wide",
                detail=(
                    f"The last lead event was {signals.days_since_last_lead} days "
                    f"ago, after {signals.leads_in_prior_window:.0f} in the "
                    "ninety days before it. A site that was converting and "
                    "stopped is usually a broken tag rather than a broken "
                    "offer — and until it is checked, every lead number on "
                    "this page is wrong."
                ),
                evidence=(
                    f"facts_ga4_events: last lead {signals.days_since_last_lead} days ago",
                ),
            )
        )

    if (
        signals.indexable_now is not None
        and signals.indexable_before
        and signals.indexable_now
        < signals.indexable_before * (1 - PAGE_DROP_SHARE)
    ):
        lost = signals.indexable_before - signals.indexable_now
        share = lost / signals.indexable_before * 100
        found.append(
            Incident(
                uid=f"{slug}-{month}-pages-dropped",
                title=f"{lost} indexable pages have gone since the last crawl",
                scope="Site-wide",
                detail=(
                    f"{signals.indexable_before} indexable pages on "
                    f"{signals.crawl_before_date}, {signals.indexable_now} now — "
                    f"{share:.0f}% fewer. A drop this size is a deployment, a "
                    "robots rule or a migration, not drift, and every ranking "
                    "on this page is measured against a site that no longer "
                    "exists."
                ),
                evidence=(
                    f"facts_crawl_page_snapshots: {signals.indexable_before} -> "
                    f"{signals.indexable_now} indexable",
                ),
            )
        )

    for brand, pages in signals.foreign_brands:
        found.append(
            Incident(
                uid=f"{slug}-{month}-wrong-brand",
                title="The site's markup names a different company",
                scope="Site-wide",
                detail=(
                    f"Organization schema on {pages} pages names “{brand}”. "
                    "Structured data is what an engine reads to decide who a "
                    "site belongs to, so this is telling them the site is "
                    "somebody else's."
                ),
                evidence=(
                    f"facts_crawl_page_schema: Organization name “{brand}” on "
                    f"{pages} of {signals.pages_with_organization} pages",
                ),
            )
        )
        # One card, not one per wrong name: it is the same fault.
        break

    return found
