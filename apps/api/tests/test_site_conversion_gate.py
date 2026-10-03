"""Gate 1: is the site converting at the level the plan requires?

The rule asked one question — did the rate fall while traffic held — which
only catches a site that got worse recently. A site that has converted badly
since onboarding never tripped it, and that is the client most in need of it.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.services.decision_impact import SiteBusinessContext
from app.services.lever_engine import _conversion_portfolio

END = date(2026, 8, 31)
START = END - timedelta(days=29)
PREV_END = START - timedelta(days=1)


def _site(rate=2.0, leads=40, goal=50):
    return SiteBusinessContext(
        site_lead_rate_pct=rate,
        period_sessions=2000.0,
        period_leads=leads,
        period_lead_goal=goal,
        p90_page_sessions=500.0,
    )


def _dashboard(sessions_now=2000, sessions_prev=2000, leads_now=20, goal=50):
    return {
        "traffic": {"ga4_sessions": {"current": sessions_now, "previous": sessions_prev}},
        "conversions": {"leads": {"current": leads_now}, "period_lead_goal": goal},
    }


def _setup(db, client, *, now_sessions, now_leads, prev_sessions, prev_leads, baseline=None):
    db.add(
        ConversionDefinition(
            id=uuid4(),
            client_id=client.id,
            event_name="generate_lead",
            conversion_name="Lead",
            conversion_type="lead",
            is_primary=True,
            active=True,
        )
    )
    for on, sessions, leads in ((END, now_sessions, now_leads), (PREV_END, prev_sessions, prev_leads)):
        db.add(
            FactGa4Traffic(
                id=uuid4(),
                client_id=client.id,
                date=on,
                raw_url="https://example.com/",
                normalized_url="https://example.com",
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                sessions=Decimal(sessions),
                active_users=Decimal(sessions),
                views=Decimal(sessions),
            )
        )
        if leads:
            db.add(
                FactGa4Event(
                    id=uuid4(),
                    client_id=client.id,
                    date=on,
                    raw_url="https://example.com/",
                    normalized_url="https://example.com",
                    session_source="google",
                    session_medium="organic",
                    channel=OrganicChannel.ORGANIC_SEARCH,
                    event_name="generate_lead",
                    event_count=leads,
                )
            )
    if baseline is not None:
        client.baseline_lead_rate_pct = baseline
    db.commit()


def _run(db, client, dashboard):
    return _conversion_portfolio(
        db, client, from_date=START, to_date=END, dashboard=dashboard, site=_site()
    )


def test_a_falling_rate_with_steady_traffic_still_fires(db, client_a):
    """The original rule, unchanged: something broke recently."""
    _setup(db, client_a, now_sessions=1000, now_leads=5, prev_sessions=1000, prev_leads=50)

    finding = _run(db, client_a, _dashboard(1000, 1000, leads_now=50, goal=40))

    assert finding is not None
    assert finding.diagnosis == "Managed traffic holding but lead rate falling"
    assert "falling" in finding.evidence_json["triggers"]


def test_a_site_that_never_converted_well_is_now_found(db, client_a):
    """Steady and bad. The old rule saw nothing here because nothing changed."""
    # Enough traffic that 0.2% against a 2% baseline is a finding and not a
    # small sample: at the prior rate these sessions expect 12.5 leads.
    _setup(
        db,
        client_a,
        now_sessions=2500,
        now_leads=5,
        prev_sessions=2500,
        prev_leads=5,
        baseline=Decimal("2.0"),
    )

    finding = _run(db, client_a, _dashboard(2500, 2500, leads_now=5, goal=40))

    assert finding is not None
    assert "below_baseline" in finding.evidence_json["triggers"]
    assert "baseline" in finding.diagnosis


def test_behind_the_plan_is_a_finding_even_when_nothing_is_falling(db, client_a):
    """The number promised to the client is the one that matters most to them."""
    _setup(db, client_a, now_sessions=1000, now_leads=20, prev_sessions=1000, prev_leads=20)

    finding = _run(db, client_a, _dashboard(1000, 1000, leads_now=20, goal=50))

    assert finding is not None
    assert finding.evidence_json["triggers"] == ["behind_plan"]
    assert "20 leads against a goal of 50" in finding.diagnosis
    # The gap is the expected result; the action names where to go and get it.
    assert finding.evidence_json["expected_impact"] == "the 30-lead gap to plan"
    assert finding.evidence_json["cause"] == "behind_plan"
    assert "Work the conversion path on" in finding.recommended_action


def test_a_healthy_site_produces_nothing(db, client_a):
    _setup(
        db,
        client_a,
        now_sessions=1000,
        now_leads=45,
        prev_sessions=1000,
        prev_leads=44,
        baseline=Decimal("2.0"),
    )

    assert _run(db, client_a, _dashboard(1000, 1000, leads_now=45, goal=50)) is None


def test_slightly_behind_plan_is_a_normal_month(db, client_a):
    """At 85% of goal the rule stays quiet; the bar is 80%."""
    _setup(db, client_a, now_sessions=1000, now_leads=43, prev_sessions=1000, prev_leads=43)

    assert _run(db, client_a, _dashboard(1000, 1000, leads_now=43, goal=50)) is None


def test_a_traffic_collapse_is_not_reported_as_a_conversion_problem(db, client_a):
    """Leads fell because traffic fell. Blaming the conversion path misleads."""
    _setup(db, client_a, now_sessions=300, now_leads=6, prev_sessions=1000, prev_leads=20)

    finding = _run(db, client_a, _dashboard(300, 1000, leads_now=6, goal=0))

    # The rate held at 2%, so neither the fall nor the baseline trigger applies,
    # and no goal was set to be behind.
    assert finding is None


def test_three_problems_report_as_one_finding(db, client_a):
    """Three findings in different units is the noise this is being pulled out of."""
    _setup(
        db,
        client_a,
        now_sessions=1000,
        now_leads=2,
        prev_sessions=1000,
        prev_leads=50,
        baseline=Decimal("4.0"),
    )

    finding = _run(db, client_a, _dashboard(1000, 1000, leads_now=2, goal=50))

    assert finding is not None
    assert set(finding.evidence_json["triggers"]) == {"falling", "below_baseline", "behind_plan"}
    # The acute one leads.
    assert finding.diagnosis == "Managed traffic holding but lead rate falling"


def test_no_conversions_configured_means_no_finding(db, client_a):
    assert _run(db, client_a, _dashboard()) is None


# --- T1: small samples ------------------------------------------------------


def test_a_rate_that_moved_on_a_handful_of_leads_is_not_a_finding(db, client_a):
    """A rate halving on four expected leads halved on noise, and saying so to
    a client costs more credibility than staying quiet."""
    _setup(db, client_a, now_sessions=200, now_leads=0, prev_sessions=200, prev_leads=4)

    # 200 sessions at the prior 2% rate expects 4 leads, under the minimum 10.
    assert _run(db, client_a, _dashboard(200, 200, leads_now=0, goal=0)) is None


def test_the_same_shape_at_volume_does_fire(db, client_a):
    _setup(db, client_a, now_sessions=2000, now_leads=2, prev_sessions=2000, prev_leads=40)

    finding = _run(db, client_a, _dashboard(2000, 2000, leads_now=2, goal=0))

    assert finding is not None
    assert "falling" in finding.evidence_json["triggers"]
    assert finding.evidence_json["expected_leads"] == 40.0


def test_below_baseline_expects_against_the_baseline_not_the_slump(db, client_a):
    """Using the previous rate for both would silence this on exactly the
    client it exists for: a site that always converted badly has a low
    previous rate, so it would never expect enough leads to qualify."""
    _setup(
        db,
        client_a,
        now_sessions=1000,
        now_leads=2,
        prev_sessions=1000,
        prev_leads=2,
        baseline=Decimal("2.0"),
    )

    finding = _run(db, client_a, _dashboard(1000, 1000, leads_now=2, goal=0))

    assert finding is not None
    assert "below_baseline" in finding.evidence_json["triggers"]
    # 0.2% prior expects 2 leads; 2% baseline expects 20.
    assert finding.evidence_json["expected_leads"] == 2.0
    assert finding.evidence_json["expected_leads_at_baseline"] == 20.0


def test_paid_and_direct_do_not_count_toward_the_organic_rate(db, client_a):
    """The query never scoped to managed channels despite the name, so a paid
    campaign ending read as the organic conversion path breaking."""
    from app.models.config import OrganicChannel
    from app.services.lever_engine import _managed_sessions

    db.add(
        FactGa4Traffic(
            id=uuid4(),
            client_id=client_a.id,
            date=END,
            raw_url="https://example.com/",
            normalized_url="https://example.com",
            session_source="google",
            session_medium="cpc",
            channel=OrganicChannel.OTHER,
            sessions=Decimal("5000"),
            active_users=Decimal("5000"),
            views=Decimal("5000"),
        )
    )
    _setup(db, client_a, now_sessions=400, now_leads=8, prev_sessions=400, prev_leads=8)

    assert _managed_sessions(db, client_a.id, (START, END)) == 400.0


def test_leads_are_marked_raw_because_no_qualified_field_exists(db, client_a):
    _setup(db, client_a, now_sessions=2000, now_leads=2, prev_sessions=2000, prev_leads=40)

    finding = _run(db, client_a, _dashboard(2000, 2000, leads_now=2, goal=0))

    assert finding.evidence_json["lead_source"] == "raw"
