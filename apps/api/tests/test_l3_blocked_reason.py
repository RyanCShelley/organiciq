"""L3 names the input that is actually missing.

The reason was hardcoded prose: every client was told it had "no conversion
pages declared to route to", including the ones that had declared them. That
sends somebody to fix a thing that is not broken, and leaves the real gap —
nothing recording which landing pages are top of funnel — unnamed.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.decisions.triage import LeadSignals, Status, assess_leads
from app.models.client import Client
from app.models.config import ClientConversionPage
from app.services.triage_signals import lead_signals as read_lead_signals


def _l3(signals: LeadSignals):
    return next(t for t in assess_leads(signals, thresholds={}) if t.id == "L3")


def test_l3_uses_the_reason_it_was_given():
    result = _l3(
        LeadSignals(
            conversions_configured=True,
            next_step_measurable=False,
            next_step_blocked_by="nothing says which pages are top of funnel",
        )
    )
    assert result.status is Status.BLOCKED
    assert result.missing == "nothing says which pages are top of funnel"


def test_l3_falls_back_when_no_reason_is_supplied():
    # The fallback only fires if a caller forgets to supply one; the readers
    # in triage_signals always do.
    result = _l3(LeadSignals(conversions_configured=True))
    assert result.missing == "no conversion pages declared to route to"


def test_a_client_with_no_conversion_pages_is_told_to_declare_them(
    db: Session, client_a: Client
):
    signals = read_lead_signals(db, client_a, today=date.today())
    assert signals.next_step_blocked_by == "no conversion pages declared to route to"


def test_a_client_with_conversion_pages_is_told_the_real_gap(
    db: Session, client_a: Client
):
    db.add(
        ClientConversionPage(
            client_id=client_a.id,
            normalized_url="/contact",
            label="Contact",
            is_primary=True,
        )
    )
    db.commit()

    signals = read_lead_signals(db, client_a, today=date.today())
    reason = signals.next_step_blocked_by or ""
    # Not "you have none" — they have one. The gap has moved on to the stages.
    assert "1 conversion page declared" in reason
    assert "confirmed funnel stage" in reason

    db.add(
        ClientConversionPage(
            client_id=client_a.id, normalized_url="/demo", label="Demo"
        )
    )
    db.commit()
    assert "2 conversion pages declared" in (
        read_lead_signals(db, client_a, today=date.today()).next_step_blocked_by or ""
    )
