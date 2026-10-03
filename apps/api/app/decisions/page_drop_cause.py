"""Why a converting page stopped converting. Playbook lever 2.

Leads are sessions times conversion rate, so the first question is always
which side moved. If the traffic went, the page is not the problem and
rewriting it wastes the month — that case belongs to decay or to the
keyword that stopped ranking.

Only once the sessions held is it worth asking what changed about the page,
and then in the order a cause is cheapest to confirm: who is arriving, on
what device, whether the page itself changed, whether it got slower.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.decisions.prescription import Prescription, Step

#: Sessions moving less than this held. Leads are noisy; traffic is not.
SESSIONS_HELD_PCT = 15.0
#: A conversion rate has to fall this far to be worth a card.
RATE_DROP_PCT = 20.0
#: Mobile converting below this share of desktop is a mobile problem.
MOBILE_RATE_SHARE = 0.5
#: Mobile LCP worse than this is slow enough to cost conversions.
SLOW_LCP_SECONDS = 4.0


@dataclass(frozen=True)
class PageDropSignals:
    page_url: str
    sessions_now: float
    sessions_before: float
    rate_now: float
    rate_before: float
    leads_lost: float
    #: Share of sessions from informational queries, now and before. None
    #: where query data is not joined to the page.
    informational_share_now: float | None = None
    informational_share_before: float | None = None
    #: Conversion rate by device. None where GA4 carries no device dimension,
    #: which is currently always — see the data defects note.
    mobile_rate: float | None = None
    desktop_rate: float | None = None
    desktop_leads: float = 0.0
    #: When the page was last modified, if the crawl saw it change.
    changed_on: str | None = None
    #: Whether the crawl can still find a form or call to action.
    conversion_elements: int | None = None
    mobile_lcp_seconds: float | None = None


def _fell(now: float, before: float, by_pct: float) -> bool:
    if before <= 0:
        return False
    return ((before - now) / before) * 100.0 >= by_pct


def classify_page_drop(signals: PageDropSignals) -> Prescription | None:
    """The cause, or None when nothing moved enough to be worth a card."""
    evidence = {
        "sessions_now": round(signals.sessions_now, 1),
        "sessions_before": round(signals.sessions_before, 1),
        "lead_rate_now_pct": round(signals.rate_now, 2),
        "lead_rate_before_pct": round(signals.rate_before, 2),
        "leads_lost": round(signals.leads_lost, 1),
    }

    # 1. Traffic, not the page. Hand it to the lever that can do something.
    if _fell(signals.sessions_now, signals.sessions_before, SESSIONS_HELD_PCT):
        return Prescription(
            cause="sessions_fell",
            evidence=evidence,
            steps=[
                Step(
                    "Treat this as a traffic problem, not a page problem",
                    target=signals.page_url,
                    detail="The conversion rate held; the visitors stopped arriving. "
                    "Work the decay or ranking finding for this page instead — "
                    "rewriting the page cannot buy back traffic it is not getting.",
                ),
            ],
            expected_impact=f"about {signals.leads_lost:.0f} leads a period, via traffic",
            verify_metric="page_sessions",
            verify_after_days=28,
            routed_to="decaying_page",
        )

    if not _fell(signals.rate_now, signals.rate_before, RATE_DROP_PCT):
        return None

    # 2. The page itself lost its way to convert. Cheapest to confirm, and
    #    the most common cause of a rate falling off a cliff.
    if signals.conversion_elements == 0:
        return Prescription(
            cause="page_changed",
            evidence={**evidence, "conversion_elements": 0},
            steps=[
                Step(
                    "Put the form or call to action back on this page",
                    target=signals.page_url,
                    detail="The crawl finds no form, no phone link and no call-to-action "
                    "button. Something removed it.",
                ),
            ],
            expected_impact=f"about {signals.leads_lost:.0f} leads a period",
            verify_metric="page_lead_rate",
            verify_after_days=28,
        )

    if signals.changed_on:
        return Prescription(
            cause="page_changed",
            evidence={**evidence, "changed_on": signals.changed_on},
            steps=[
                Step(
                    "Compare the page against the version from before the drop",
                    target=signals.page_url,
                    detail=f"It changed on {signals.changed_on}, which is when the rate "
                    "fell. Restore whatever proof, section or call to action went.",
                    human=True,
                ),
            ],
            expected_impact=f"about {signals.leads_lost:.0f} leads a period",
            verify_metric="page_lead_rate",
            verify_after_days=28,
        )

    # 3. Mobile, where the data exists to say so.
    if (
        signals.mobile_rate is not None
        and signals.desktop_rate
        and signals.desktop_leads >= 10
        and signals.mobile_rate < signals.desktop_rate * MOBILE_RATE_SHARE
    ):
        return Prescription(
            cause="mobile_regression",
            evidence={
                **evidence,
                "mobile_rate_pct": round(signals.mobile_rate, 2),
                "desktop_rate_pct": round(signals.desktop_rate, 2),
            },
            steps=[
                Step(
                    "Put the call to action on the first mobile screen",
                    target=signals.page_url,
                    detail="Add a sticky call to action and a tap-to-call link.",
                ),
                Step(
                    "Cut the form to four fields or fewer on mobile",
                    target=signals.page_url,
                ),
            ],
            expected_impact=f"about {signals.leads_lost:.0f} leads a period",
            verify_metric="mobile_lead_rate",
            verify_after_days=28,
        )

    if signals.mobile_lcp_seconds and signals.mobile_lcp_seconds > SLOW_LCP_SECONDS:
        return Prescription(
            cause="speed_regression",
            evidence={**evidence, "mobile_lcp_seconds": signals.mobile_lcp_seconds},
            steps=[
                Step(
                    "Fix the largest contentful paint element on mobile",
                    target=signals.page_url,
                    detail=f"It currently paints at {signals.mobile_lcp_seconds:.1f}s. "
                    "Usually an oversized hero image or a render-blocking script.",
                ),
            ],
            expected_impact=f"about {signals.leads_lost:.0f} leads a period",
            verify_metric="mobile_lcp",
            verify_after_days=28,
        )

    # 4. Who is arriving changed, so the page is converting a different crowd.
    if (
        signals.informational_share_now is not None
        and signals.informational_share_before is not None
        and signals.informational_share_now > signals.informational_share_before + 15.0
    ):
        return Prescription(
            cause="traffic_mix_shifted",
            evidence={
                **evidence,
                "informational_share_now_pct": round(signals.informational_share_now, 1),
                "informational_share_before_pct": round(
                    signals.informational_share_before, 1
                ),
            },
            steps=[
                Step(
                    "Leave the page's main offer alone",
                    target=signals.page_url,
                    detail="The rate fell because the visitors changed, not the page.",
                ),
                Step(
                    "Add a mid-funnel offer for the new visitors",
                    target=signals.page_url,
                    detail="A checklist, grader or case study, linked through to the "
                    "money page.",
                ),
            ],
            expected_impact=f"about {signals.leads_lost:.0f} leads a period",
            verify_metric="page_lead_rate",
            verify_after_days=28,
        )

    # 5. Nothing matched. Still not "review it": a named experiment.
    return Prescription(
        cause="undetermined",
        evidence=evidence,
        steps=[
            Step(
                "Run an A/B test on this page's main call to action",
                target=signals.page_url,
                detail="None of the checks found a cause: traffic held, the page has "
                "not changed, and no device or speed signal explains it. Log the test "
                "in the SEO Experiment Tracker.",
            ),
            Step(
                "Watch five session recordings of visitors who did not convert",
                target=signals.page_url,
                human=True,
            ),
        ],
        expected_impact=f"about {signals.leads_lost:.0f} leads a period",
        verify_metric="page_lead_rate",
        verify_after_days=28,
    )
