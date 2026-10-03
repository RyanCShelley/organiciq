"""Every finding says what to do, and names the cause it decided on.

The reports answer the gates — leads down, page slipped. The engine exists
to say what to do about it, and a card reading "review traffic and UX" has
handed that back to the reader.
"""

from __future__ import annotations

import pytest

from app.decisions.page_drop_cause import PageDropSignals, classify_page_drop
from app.decisions.prescription import CAUSES, Prescription, Step
from app.decisions.tracking_cause import TrackingSignals, classify_tracking_break


# ── The contract ──


def test_a_step_that_says_review_is_rejected():
    for text in ("Review the page", "Look at the form", "Investigate the drop"):
        with pytest.raises(ValueError, match="not an action"):
            Prescription(cause="undetermined", steps=[Step(text)])


def test_a_prescription_with_no_steps_is_rejected():
    with pytest.raises(ValueError, match="no steps"):
        Prescription(cause="undetermined", steps=[])


def test_an_unknown_cause_is_rejected():
    with pytest.raises(ValueError, match="unknown cause"):
        Prescription(cause="vibes", steps=[Step("Do the thing")])


def test_every_cause_has_a_sentence_explaining_it():
    assert all(text and text[0].isupper() for text in CAUSES.values())


# ── Lever 1: which part of tracking broke ──


def _tracking(**kwargs):
    base = dict(
        sessions_now=500.0,
        sessions_before=500.0,
        search_clicks_now=400.0,
        search_clicks_before=420.0,
        leads_now=0.0,
        crm_leads_now=None,
    )
    base.update(kwargs)
    return classify_tracking_break(TrackingSignals(**base))


def test_sessions_gone_while_google_still_reports_clicks_is_the_tag():
    """Search clicks are the witness that does not depend on our own tag."""
    p = _tracking(sessions_now=20.0)
    assert p.cause == "analytics_tag_broken"
    assert "Re-add the GA4 tag" in p.steps[0].text


def test_sessions_and_clicks_both_gone_is_not_the_tag():
    """The site really did lose its traffic. Re-adding the tag fixes nothing."""
    assert _tracking(sessions_now=20.0, search_clicks_now=10.0).cause != "analytics_tag_broken"


def test_the_crm_still_receiving_means_the_event_not_the_form():
    p = _tracking(crm_leads_now=12.0)
    assert p.cause == "conversion_event_broken"
    assert any("Republish the tag manager" in step.text for step in p.steps)


def test_neither_the_crm_nor_ga4_means_the_form():
    p = _tracking(crm_leads_now=0.0)
    assert p.cause == "form_broken"
    assert any("spam filter" in step.text for step in p.steps)


def test_one_quiet_page_while_the_rest_convert_is_a_partial_break():
    p = _tracking(leads_now=8.0, silent_pages=("https://x/quote",))
    assert p.cause == "partial_tracking_break"
    assert p.steps[0].target == "https://x/quote"


def test_with_no_crm_it_asks_for_the_one_test_that_separates_them():
    """Guessing between the form and the event wastes the afternoon either way."""
    p = _tracking()
    assert p.evidence["crm_connected"] is False
    assert "DebugView and the inbox together" in p.steps[0].text
    assert "No CRM is connected" in p.steps[0].detail


# ── Lever 2: which side of leads = sessions x rate moved ──


def _drop(**kwargs):
    base = dict(
        page_url="https://x/services",
        sessions_now=500.0,
        sessions_before=500.0,
        rate_now=0.5,
        rate_before=3.0,
        leads_lost=12.0,
        conversion_elements=3,
    )
    base.update(kwargs)
    return classify_page_drop(PageDropSignals(**base))


def test_traffic_gone_is_routed_rather_than_prescribed():
    """Rewriting a page cannot buy back traffic it is not getting."""
    p = _drop(sessions_now=100.0, rate_now=3.0)
    assert p.cause == "sessions_fell"
    assert p.routed_to == "decaying_page"
    assert "not a page problem" in p.steps[0].text


def test_a_page_that_lost_its_form_says_exactly_that():
    p = _drop(conversion_elements=0)
    assert p.cause == "page_changed"
    assert "Put the form or call to action back" in p.steps[0].text


def test_a_steady_page_and_a_steady_rate_is_not_a_finding():
    assert _drop(rate_now=2.9, leads_lost=0.0) is None


def test_no_cause_found_still_names_an_experiment():
    """"Undetermined" is not permission to say "review it"."""
    p = _drop()
    assert p.cause == "undetermined"
    assert "A/B test" in p.steps[0].text
    assert p.verify_metric == "page_lead_rate"


def test_every_prescription_can_be_verified():
    for p in (_tracking(), _tracking(sessions_now=20.0), _drop(), _drop(conversion_elements=0)):
        assert p.verify_metric
        assert p.verify_after_days > 0
        assert p.expected_impact
