"""Where a site-wide lead drop is actually concentrated. Playbook 3.

"Leads are down" is the report. The engine's job is to say which part of
the site lost them, because the answer decides whether anyone touches the
site at all: a drop sitting in one page group is that page's problem and
belongs to lever 2, a drop spread evenly is something global that changed,
and a drop that matches last year is the calendar.

Segments the playbook asks for and we cannot read: device and new versus
returning, which GA4 is not queried for, and qualified-versus-raw leads,
which needs a CRM. Those become named checks rather than silence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.decisions.prescription import Prescription, Step

#: One page group holding this much of the loss is that page's problem.
CONCENTRATION_SHARE = 0.6
#: Within this of last year's fall, it is the calendar.
SEASONAL_TOLERANCE_PCT = 25.0


@dataclass(frozen=True)
class SiteConversionSignals:
    leads_now: float
    leads_before: float
    #: Leads lost per page group, biggest first.
    loss_by_group: list[tuple[str, float]] = field(default_factory=list)
    #: Leads lost per channel, biggest first.
    loss_by_channel: list[tuple[str, float]] = field(default_factory=list)
    #: The same period a year ago, when there is a year of history.
    leads_year_ago: float | None = None
    leads_year_before_that: float | None = None
    #: Pages with the most traffic and the worst conversion, worst first.
    #: Where a site that is simply short of plan buys the gap back cheapest.
    weakest_pages: list[tuple[str, float, float]] = field(default_factory=list)
    #: Leads the plan expects this period, when there is a goal.
    period_goal: float | None = None


def classify_site_conversion(signals: SiteConversionSignals) -> Prescription:
    lost = signals.leads_before - signals.leads_now
    evidence = {
        "leads_now": round(signals.leads_now, 1),
        "leads_before": round(signals.leads_before, 1),
        "leads_lost": round(lost, 1),
        "loss_by_group": [[name, round(value, 1)] for name, value in signals.loss_by_group[:5]],
        "loss_by_channel": [
            [name, round(value, 1)] for name, value in signals.loss_by_channel[:5]
        ],
    }

    # 0. Nothing fell. A site short of plan that is not getting worse has a
    #    different problem from one that broke last month, and telling
    #    someone to find what changed sends them looking for nothing.
    if lost <= 0:
        shortfall = (
            (signals.period_goal - signals.leads_now)
            if signals.period_goal
            else 0.0
        )
        steps: list[Step] = []
        for url, sessions, rate in signals.weakest_pages[:3]:
            steps.append(
                Step(
                    f"Work the conversion path on {url}",
                    target=url,
                    detail=f"{sessions:,.0f} sessions a period converting at "
                    f"{rate:.2f}%. The traffic is already arriving, so this is the "
                    "cheapest place to buy the gap back.",
                )
            )
        if not steps:
            steps.append(
                Step(
                    "Pick the three pages with the most traffic and the worst "
                    "conversion, and work those first",
                    detail="No page has enough traffic for its rate to be read "
                    "reliably, so the shortfall is a traffic problem before it is a "
                    "conversion one.",
                    human=True,
                )
            )
        return Prescription(
            cause="behind_plan",
            evidence={**evidence, "period_goal": signals.period_goal},
            steps=steps,
            expected_impact=(
                f"the {shortfall:.0f}-lead gap to plan"
                if shortfall > 0
                else "the gap to plan"
            ),
            verify_metric="site_leads",
            verify_after_days=28,
        )

    # 1. The calendar. Checked first because every other cause is a reason to
    #    change something, and this one is a reason not to.
    if (
        signals.leads_year_ago is not None
        and signals.leads_year_before_that
        and signals.leads_year_before_that > 0
        and lost > 0
    ):
        last_year_fall = (
            (signals.leads_year_before_that - signals.leads_year_ago)
            / signals.leads_year_before_that
        ) * 100.0
        this_fall = (lost / signals.leads_before * 100.0) if signals.leads_before else 0.0
        if last_year_fall > 0 and abs(this_fall - last_year_fall) <= SEASONAL_TOLERANCE_PCT:
            return Prescription(
                cause="seasonal",
                evidence={
                    **evidence,
                    "fall_pct": round(this_fall, 1),
                    "fall_pct_last_year": round(last_year_fall, 1),
                },
                steps=[
                    Step(
                        "Record this as seasonal and hold the plan",
                        detail=f"Leads fell {this_fall:.0f}% and fell {last_year_fall:.0f}% "
                        "over the same weeks last year. Spending the month chasing it "
                        "buys back something the calendar returns on its own.",
                        human=True,
                    ),
                ],
                expected_impact="No action — the comparison is the finding",
                verify_metric="leads_year_over_year",
                verify_after_days=56,
            )

    # 2. Concentrated. Hand it to the page rather than describing the site.
    if signals.loss_by_group and lost > 0:
        top_name, top_loss = signals.loss_by_group[0]
        share = top_loss / lost if lost else 0.0
        if share >= CONCENTRATION_SHARE:
            return Prescription(
                cause="drop_concentrated",
                evidence={**evidence, "top_group": top_name, "top_group_share": round(share, 2)},
                steps=[
                    Step(
                        f"Work the finding for {top_name} rather than the site",
                        target=top_name,
                        detail=f"{share:.0%} of the {lost:.0f} lost leads are on this one "
                        "page group. Nothing site-wide explains a loss that sits in one "
                        "place.",
                    ),
                ],
                expected_impact=f"about {top_loss:.0f} of the {lost:.0f} leads lost",
                verify_metric="page_group_leads",
                verify_after_days=28,
                routed_to="converting_page_dropped",
            )

    # 3. Even across the site: something global changed.
    return Prescription(
        cause="drop_sitewide",
        evidence=evidence,
        steps=[
            Step(
                "Check what changed site-wide in the weeks the drop began",
                detail="The header and navigation, the global form or chat widget, the "
                "consent banner, and any offer or pricing change. The loss is spread "
                "across pages, so the cause is on all of them.",
                human=True,
            ),
            Step(
                "Test the call to action in the header and on the top five landing pages",
                detail="If nothing changed, this is the cheapest way to move a rate that "
                "is down everywhere at once.",
            ),
            Step(
                "Compare mobile against desktop and new against returning by hand",
                detail="GA4 is not queried for device or visitor type, so those two "
                "segments cannot be ruled out from our data.",
                human=True,
            ),
        ],
        expected_impact=f"about {lost:.0f} leads a period",
        verify_metric="site_lead_rate",
        verify_after_days=28,
    )
