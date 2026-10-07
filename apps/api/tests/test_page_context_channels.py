"""Page sessions and leads must come from the channels the plan manages.

The trigger that picks a page counts organic sessions only. The valuation
that decides what fixing it is worth read every channel. ACC Tek's
homepage took 103 organic sessions a month and converted none of them, so
the gate selected it; the shortfall was then computed against 5 leads from
every channel, four of them referral, which made the page look like it was
over-performing and scored the client's only real action at zero.

`_leads_by_page` has carried a warning about exactly this since it was
written. The other path did not.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models.ga4 import FactGa4Event, FactGa4Traffic, OrganicChannel
from app.services.decision_impact import load_page_business_contexts

URL = "https://example.com/"
MANAGED = (OrganicChannel.ORGANIC_SEARCH, OrganicChannel.AI_REFERRAL)


def _seed(db, client_id, on):
    def traffic(channel, sessions):
        db.add(
            FactGa4Traffic(
                id=uuid4(),
                client_id=client_id,
                date=on,
                raw_url=URL,
                normalized_url=URL,
                session_source="x",
                session_medium="y",
                channel=channel,
                sessions=Decimal(sessions),
                active_users=Decimal(sessions),
                views=Decimal(sessions),
                engaged_sessions=Decimal(sessions),
            )
        )

    def lead(channel, count):
        db.add(
            FactGa4Event(
                id=uuid4(),
                client_id=client_id,
                date=on,
                raw_url=URL,
                normalized_url=URL,
                session_source="x",
                session_medium="y",
                channel=channel,
                event_name="generate_lead",
                event_count=count,
            )
        )

    # The shape ACC Tek's homepage is in: organic arrives and converts
    # nothing, while referral converts.
    traffic(OrganicChannel.ORGANIC_SEARCH, 103)
    traffic(OrganicChannel.DIRECT_UNATTRIBUTED, 315)
    traffic(OrganicChannel.REFERRAL, 64)
    lead(OrganicChannel.REFERRAL, 4)
    lead(OrganicChannel.PAID_SEARCH, 1)
    db.commit()


def _load(db, client_id, period, channels):
    return load_page_business_contexts(
        db,
        client_id=client_id,
        period=period,
        lead_events=["generate_lead"],
        normalized_urls=[URL],
        channels=channels,
    )


def test_only_managed_channels_are_counted(db, client_a):
    end = date.today()
    _seed(db, client_a.id, end)
    ctx = _load(db, client_a.id, (end - timedelta(days=29), end), MANAGED)[URL]
    assert ctx.ga4_sessions == 103, "direct and referral sessions are not organic"
    assert ctx.ga4_leads == 0, "a referral conversion is not an organic one"


def test_a_page_that_only_converts_elsewhere_still_reads_as_leaking(db, client_a):
    """The bug, stated as its consequence: this page must not look like it
    converts, or the action to fix it is valued at zero and discarded."""
    end = date.today()
    _seed(db, client_a.id, end)
    ctx = _load(db, client_a.id, (end - timedelta(days=29), end), MANAGED)[URL]
    assert ctx.page_lead_rate_pct == 0.0


def test_without_a_channel_filter_every_channel_is_counted(db, client_a):
    """The old behaviour, kept honest: `channels=None` is the unfiltered
    read, so nobody reaches for it thinking it is scoped."""
    end = date.today()
    _seed(db, client_a.id, end)
    ctx = _load(db, client_a.id, (end - timedelta(days=29), end), None)[URL]
    assert ctx.ga4_sessions == 482
    assert ctx.ga4_leads == 5


# ── The window ──


def test_the_headline_and_the_evidence_count_the_same_days(db, client_a):
    """One card said "54 sessions and no conversions" and, three lines
    down, "sessions 103". The headline came from the page context, built
    over the Search Console window, and the evidence from the T1 gate,
    built over the GA4 window. ACC Tek's Search Console facts stopped on
    22 Sep, so one was 15 days and the other 30 — and the shortfall that
    decided the action's value was computed on the short one."""
    end = date.today()
    for day_offset in range(30):
        _seed(db, client_a.id, end - timedelta(days=day_offset))

    full = _load(db, client_a.id, (end - timedelta(days=29), end), MANAGED)[URL]
    half = _load(db, client_a.id, (end - timedelta(days=14), end), MANAGED)[URL]

    assert full.ga4_sessions == 103 * 30
    assert half.ga4_sessions == 103 * 15
    assert full.ga4_sessions != half.ga4_sessions, (
        "the window has to matter, or this test proves nothing"
    )
