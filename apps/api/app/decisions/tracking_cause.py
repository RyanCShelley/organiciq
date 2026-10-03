"""Which part of tracking broke. Playbook lever 1.

"No conversions recorded" is four different faults wearing one label, and
they have four different fixes. Re-adding the GA4 tag does nothing if the
tag is fine and the form is throwing a script error; testing the form
wastes an afternoon if the whole container stopped publishing.

The order matters: each check rules out everything above it, so the first
one that matches is the cause. Sessions are checked before events because
a site-wide tag failure takes the events with it and would otherwise look
like an event fault.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.decisions.prescription import Prescription, Step

#: Sessions down by more than this while search clicks hold is the tag, not
#: the market. A real traffic collapse drags clicks with it.
SESSION_COLLAPSE_PCT = 80.0


@dataclass(frozen=True)
class TrackingSignals:
    sessions_now: float
    sessions_before: float
    #: Search clicks over the same window, as the independent witness: they
    #: come from Google, not from the tag we are testing.
    search_clicks_now: float
    search_clicks_before: float
    leads_now: float
    #: Leads recorded by the CRM. None when no CRM is connected, which is a
    #: different answer from zero and must not be read as "the form is dead".
    crm_leads_now: float | None
    #: Pages that converted before and have stopped, while others still do.
    silent_pages: tuple[str, ...] = ()


def _fell(now: float, before: float, by_pct: float) -> bool:
    if before <= 0:
        return False
    return ((before - now) / before) * 100.0 >= by_pct


def classify_tracking_break(signals: TrackingSignals) -> Prescription:
    clicks_held = not _fell(
        signals.search_clicks_now, signals.search_clicks_before, SESSION_COLLAPSE_PCT
    )
    evidence = {
        "sessions_now": round(signals.sessions_now, 1),
        "sessions_before": round(signals.sessions_before, 1),
        "search_clicks_now": round(signals.search_clicks_now, 1),
        "search_clicks_before": round(signals.search_clicks_before, 1),
        "leads_now": round(signals.leads_now, 1),
        "crm_leads_now": signals.crm_leads_now,
    }

    # 1. Sessions collapsed while Google still reports clicks: the tag.
    if _fell(signals.sessions_now, signals.sessions_before, SESSION_COLLAPSE_PCT) and clicks_held:
        return Prescription(
            cause="analytics_tag_broken",
            evidence=evidence,
            steps=[
                Step(
                    "Re-add the GA4 tag to every template",
                    detail="Check the header include and the consent-mode default; a "
                    "consent banner defaulting to denied looks identical to a missing tag.",
                ),
                Step(
                    "Confirm a pageview arrives in GA4 Realtime",
                    detail="Load any page in a private window and watch Realtime.",
                ),
                Step(
                    "Note the gap dates so reports skip the missing days",
                    human=True,
                ),
            ],
            expected_impact="Restores every number in this report",
            verify_metric="ga4_sessions",
            verify_after_days=1,
        )

    # 2. One form or template quiet while the rest of the site converts.
    if signals.silent_pages and signals.leads_now > 0:
        first = signals.silent_pages[0]
        return Prescription(
            cause="partial_tracking_break",
            evidence={**evidence, "silent_pages": list(signals.silent_pages)},
            steps=[
                Step(
                    "Submit a test lead on this page and watch GA4 DebugView",
                    target=first,
                    detail="The rest of the site is still recording, so this is one "
                    "form or one template, not the tag.",
                ),
                Step(
                    "If the event does not fire, fix the trigger on this template",
                    target=first,
                    detail="A changed thank-you URL and an edited form embed both "
                    "break the trigger while leaving the page working.",
                ),
            ],
            expected_impact="Recovers the leads this page was recording",
            verify_metric="page_lead_events",
            verify_after_days=7,
        )

    # 3. Sessions normal, no lead event. The CRM says whether the form ran.
    if signals.crm_leads_now is not None and signals.crm_leads_now > 0:
        return Prescription(
            cause="conversion_event_broken",
            evidence=evidence,
            steps=[
                Step(
                    "Fix the conversion trigger",
                    detail="The CRM is still receiving submissions, so the form works "
                    "and the event does not. Check the thank-you URL and the "
                    "form-submit listener.",
                ),
                Step("Republish the tag manager container"),
                Step("Note the gap dates so reports skip the missing days", human=True),
            ],
            expected_impact="Restores lead attribution for this period",
            verify_metric="ga4_lead_events",
            verify_after_days=1,
        )

    if signals.crm_leads_now is not None:
        return Prescription(
            cause="form_broken",
            evidence=evidence,
            steps=[
                Step(
                    "Submit a test lead and record what happens",
                    detail="Neither GA4 nor the CRM has anything, so the submission "
                    "itself is failing rather than the reporting.",
                ),
                Step(
                    "Fix the form embed or the script error it throws",
                    detail="Check the browser console on submit.",
                ),
                Step(
                    "Check the CRM spam filter and notification routing",
                    detail="A filter change hides real submissions without erroring.",
                    human=True,
                ),
            ],
            expected_impact="Recovers every lead the form is currently losing",
            verify_metric="crm_leads",
            verify_after_days=1,
        )

    # No CRM connected: the form and the event cannot be told apart.
    return Prescription(
        cause="conversion_event_broken",
        evidence={**evidence, "crm_connected": False},
        steps=[
            Step(
                "Submit a test lead and check GA4 DebugView and the inbox together",
                detail="No CRM is connected, so this is the only way to tell a dead "
                "form from a dead event. Arriving in the inbox but not GA4 is the "
                "event; neither is the form.",
            ),
            Step("Fix whichever of the two the test identifies"),
        ],
        expected_impact="Restores lead measurement for this period",
        verify_metric="ga4_lead_events",
        verify_after_days=1,
    )
