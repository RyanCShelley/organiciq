"""Things that are wrong with the site, as opposed to things to grow.

Per rule: an incident does not take a slot and does not change the constraint.
A site that stopped recording leads has a broken tag, not a conversion
problem, and spending a growth slot on it would be answering the wrong
question — while saying nothing would let the engine keep prescribing
optimisation on a page nobody can convert on.

Two of them, each from a fact the warehouse already holds:

  * leads stopped — zero lead events for a fortnight, after a history of them
  * pages vanished — a fifth of the indexable pages gone since the last crawl

Both are *site-wide*. A single page losing its schema is on-page work and
belongs in the retainer.

A third was written and removed: the spec's example of a site-wide fault is
"schema that names the wrong brand", and run over the warehouse it flagged
three clients and was wrong about all three. SMA's markup names `OpenAI` and
`Google` because its blog posts cite them; Robinson Unmanned's names the
manufacturers it resells; ACCTek's names "ACC Technical Services Inc.", which
is ACCTek. Structured data says who is *mentioned* as readily as who owns the
site, and nothing in it separates a legal name from a brand name. A check that
cries wolf on every client teaches people to ignore the card, so it is not
here. It needs a signal for site identity — a publisher node tied to the
client's own domain — that the crawl does not isolate today.
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
    #: Lead events after the last counted one that a lead exclusion rule
    #: removed as test submissions, and the latest date of one.
    excluded_leads_since_last: float = 0.0
    excluded_last_lead_date: str | None = None

    indexable_now: int | None = None
    indexable_before: int | None = None
    crawl_before_date: str | None = None

    #: Kept so a reader of the record can see what the markup names, and so
    #: the signal is there if a site-identity check is built later. Nothing
    #: reports on it: see the module docstring.
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
        excluded_note = ""
        evidence = (f"facts_ga4_events: last lead {signals.days_since_last_lead} days ago",)
        if signals.excluded_leads_since_last > 0:
            excluded_note = (
                f" {signals.excluded_leads_since_last:.0f} more lead events exist since "
                f"(latest {signals.excluded_last_lead_date}) but are excluded as test "
                "submissions. If they are real, remove the exclusion; if they are "
                "tests, the silence is real."
            )
            evidence += (
                f"lead_exclusions: {signals.excluded_leads_since_last:.0f} excluded lead "
                f"events since the last counted one",
            )
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
                    f"{excluded_note}"
                ),
                evidence=evidence,
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

    return found
