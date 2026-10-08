"""Gate 0 (tracking) and the demotion of upkeep out of the Growth Action queue.

The engine used to hand a Launch client — who buys one focused action a month
— up to twenty-five findings, most of them titles, metas and schema, which the
plan already covers as Core Work every month. And it scored all of them from
lead counts without ever asking whether leads were being recorded at all.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.models.config import ConversionDefinition, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.services.decision_impact import SiteBusinessContext
from app.services.lever_engine import (
    INDEXATION_BLOCKING_SIGNALS,
    TRACKING_EXPECTED_LEADS,
    _tracking_failure_finding,
    is_core_work_signal,
)

END = date(2026, 8, 31)
WINDOW = (date(2026, 8, 2), END)


def _site(rate=2.0, leads=40, goal=50):
    """A site that converts, so impact can be expressed in leads."""
    return SiteBusinessContext(
        site_lead_rate_pct=rate,
        period_sessions=2000.0,
        period_leads=leads,
        period_lead_goal=goal,
        p90_page_sessions=500.0,
    )


def _define_lead(db, client_id, name="generate_lead"):
    db.add(
        ConversionDefinition(
            id=uuid4(),
            client_id=client_id,
            event_name=name,
            conversion_name="Lead",
            conversion_type="lead",
            is_primary=True,
            active=True,
        )
    )


def _traffic(db, client_id, on, sessions):
    db.add(
        FactGa4Traffic(
            id=uuid4(),
            client_id=client_id,
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


def _leads(db, client_id, on, count):
    db.add(
        FactGa4Event(
            id=uuid4(),
            client_id=client_id,
            date=on,
            raw_url="https://example.com/",
            normalized_url="https://example.com",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="generate_lead",
            event_count=count,
        )
    )


# --- Which technical work belongs in the queue -----------------------------


def test_only_signals_that_remove_a_page_from_search_stay_actionable():
    for signal in ("status_error", "non_indexable", "canonical_elsewhere", "broken_redirect"):
        assert signal in INDEXATION_BLOCKING_SIGNALS
        assert is_core_work_signal(signal) is False


def test_meta_and_schema_are_core_work():
    """The plan covers titles, metas, internal links and schema every month."""
    for signal in (
        "missing_meta",
        "duplicate_meta",
        "redirect_chain",
        "missing_schema",
        "invalid_schema",
        "sitemap_missing",
    ):
        assert is_core_work_signal(signal) is True


# --- Gate 0 ----------------------------------------------------------------


def test_silence_fires_when_the_tag_should_have_recorded_something(db, client_a):
    _define_lead(db, client_a.id)
    # History: 1000 sessions, 50 leads — a 5% rate.
    _traffic(db, client_a.id, END - timedelta(days=40), 1000)
    _leads(db, client_a.id, END - timedelta(days=40), 50)
    # The fortnight: plenty of traffic, nothing recorded.
    _traffic(db, client_a.id, END - timedelta(days=3), 400)
    db.commit()

    finding = _tracking_failure_finding(db, client_a, period=WINDOW, site=_site())

    assert finding is not None
    assert finding.evidence_json["expected_leads"] >= TRACKING_EXPECTED_LEADS
    assert finding.evidence_json["previously_recorded"] is True
    assert "was working before" in finding.diagnosis


def test_a_quiet_fortnight_at_a_small_client_is_not_a_tracking_failure(db, client_a):
    """Zero means nothing when zero was the likely outcome anyway."""
    _define_lead(db, client_a.id)
    # A 1% rate historically, and only 60 sessions in the window: under one
    # expected lead, so recording none is an ordinary fortnight.
    _traffic(db, client_a.id, END - timedelta(days=40), 2000)
    _leads(db, client_a.id, END - timedelta(days=40), 20)
    _traffic(db, client_a.id, END - timedelta(days=3), 60)
    db.commit()

    assert _tracking_failure_finding(db, client_a, period=WINDOW, site=_site()) is None


def test_one_recorded_lead_is_enough_to_say_the_tag_is_alive(db, client_a):
    _define_lead(db, client_a.id)
    _traffic(db, client_a.id, END - timedelta(days=40), 1000)
    _leads(db, client_a.id, END - timedelta(days=40), 50)
    _traffic(db, client_a.id, END - timedelta(days=3), 400)
    _leads(db, client_a.id, END - timedelta(days=3), 1)
    db.commit()

    assert _tracking_failure_finding(db, client_a, period=WINDOW, site=_site()) is None


def test_a_client_with_no_conversions_configured_has_not_broken_anything(db, client_a):
    """Otherwise every unconfigured client tops its own queue forever."""
    _traffic(db, client_a.id, END - timedelta(days=3), 5000)
    db.commit()

    assert _tracking_failure_finding(db, client_a, period=WINDOW, site=_site()) is None


def test_a_tag_that_never_fired_needs_more_traffic_to_be_sure(db, client_a):
    """With no history there is no rate to expect against, only volume."""
    _define_lead(db, client_a.id)
    _traffic(db, client_a.id, END - timedelta(days=3), 100)
    db.commit()
    assert _tracking_failure_finding(db, client_a, period=WINDOW, site=_site()) is None

    _traffic(db, client_a.id, END - timedelta(days=4), 900)
    db.commit()
    finding = _tracking_failure_finding(db, client_a, period=WINDOW, site=_site())
    assert finding is not None
    assert finding.evidence_json["previously_recorded"] is False
    assert "never have fired" in finding.diagnosis


def test_no_period_means_no_finding(db, client_a):
    _define_lead(db, client_a.id)
    db.commit()

    assert _tracking_failure_finding(db, client_a, period=None, site=_site()) is None


# --- Suppression, end to end ------------------------------------------------


def test_a_silent_tag_suppresses_every_other_finding(db, client_a):
    """Impact is computed from leads, so a dead tag makes every score a fiction.

    The findings stay in the payload — hiding them would make the queue look
    empty when it is only untrustworthy — but none may be promoted.
    """
    from app.models.gsc import FactGscPage
    from app.services.lever_engine import diagnose
    from tests.conftest import seed_required_sources

    start, end = WINDOW
    _define_lead(db, client_a.id)
    _traffic(db, client_a.id, end - timedelta(days=40), 1000)
    _leads(db, client_a.id, end - timedelta(days=40), 50)
    _traffic(db, client_a.id, end - timedelta(days=3), 400)
    db.add(
        FactGscPage(
            id=uuid4(),
            client_id=client_a.id,
            date=end,
            raw_url="https://example.com/",
            normalized_url="https://example.com/",
            country="",
            device="",
            impressions=Decimal("500"),
            clicks=Decimal("5"),
            ctr=Decimal("0.01"),
            average_position=Decimal("8"),
        )
    )
    db.commit()
    seed_required_sources(db, client_a.id, end)

    result = diagnose(db, client_a, from_date=start, to_date=end)

    tracking = [row for row in result.findings if row.evidence_json.get("gate") == "tracking"]
    assert len(tracking) == 1
    assert tracking[0].evidence_json["expected_leads"] == 20.0

    others = [row for row in result.findings if row.evidence_json.get("gate") != "tracking"]
    assert all(row.suppressed_by == tracking[0].rule_key for row in others)
    # Nothing is actionable while the number every score is built from is a
    # zero that may not be real.
    assert all(not row.is_recommended_action for row in others)
    # What a Launch client with one action a month should see: exactly one
    # thing to do, and it is the thing that makes everything else legible.
    # The tracking gate is a finding, not one of the seven rules that can
    # spend an action — silence is something to fix, not an hour of work.
    assert "tracking" in {row.evidence_json.get("gate") for row in result.findings}
    assert result.growth_actions == []


def test_core_work_never_becomes_a_recommended_action(db, client_a):
    """A Launch client buys one action a month; upkeep must not spend it."""
    from app.services.lever_engine import annotate_why_not_an_action, growth_actions
    from app.services.decision_types import LeverFinding
    from app.models.decision import DiagnosticLayer

    finding = LeverFinding(
        rule_key="technical:x",
        lever="technical_seo",
        stage=DiagnosticLayer.VISIBILITY,
        diagnosis="Missing core meta",
        recommended_action="",
        success_metric="",
        evidence_json={"promotion_class": "actionable", "rule_id": "2a"},
        baseline_metrics_json={},
        impact=99.0,
        confidence=90.0,
        urgency=90.0,
        effort=10.0,
        priority_score=95.0,
        core_work=True,
    )

    all_findings = annotate_why_not_an_action([finding])

    assert growth_actions(all_findings) == []
    assert all_findings[0].promotion_blocked_reason == "core work: included in the monthly plan"


# --- Every check prescribes a next move -------------------------------------


def test_every_technical_signal_prescribes_an_action():
    """The lever-level text restated the finding; a strategist needs the move."""
    from app.services.lever_engine import INDEXATION_BLOCKING_SIGNALS, TECHNICAL_ACTIONS

    detected_signals = {
        "status_error",
        "broken_redirect",
        "redirect_chain",
        "non_indexable",
        "canonical_elsewhere",
        "missing_meta",
        "duplicate_meta",
        "invalid_schema",
        "missing_schema",
        "sitemap_missing",
        "robots_blocking",
        "robots_advisory",
    }
    assert detected_signals <= set(TECHNICAL_ACTIONS)
    # Every blocking signal is covered too, or the urgent ones would fall back
    # to the generic lever text.
    assert INDEXATION_BLOCKING_SIGNALS <= set(TECHNICAL_ACTIONS)


def test_an_action_says_what_to_do_not_what_is_wrong():
    from app.services.lever_engine import TECHNICAL_ACTIONS

    for signal, action in TECHNICAL_ACTIONS.items():
        first_word = action.split()[0]
        assert first_word[0].isupper(), signal
        # An imperative, not a restatement. "Resolve the flagged issue" was the
        # old text and is exactly what this guards against.
        assert "flagged" not in action.lower(), signal


def test_the_technical_finding_carries_its_own_action(db, client_a):
    from app.services.lever_engine import TECHNICAL_ACTIONS, _make_finding
    from app.models.decision import GrowthAction

    finding = _make_finding(
        lever=GrowthAction.TECHNICAL_SEO.value,
        rule_key="k",
        diagnosis="Canonicalized elsewhere",
        evidence_json={},
        baseline_metrics_json={},
        impact=50.0,
        action_override=TECHNICAL_ACTIONS["canonical_elsewhere"],
    )

    assert finding.recommended_action == TECHNICAL_ACTIONS["canonical_elsewhere"]
    assert "Point the canonical" in finding.recommended_action


def test_the_response_says_how_far_each_source_runs(db, client_a):
    """A boolean readiness flag says a source reported. It cannot say that
    Search Console stopped a fortnight ago while GA4 is current, which is
    the difference between a run worth reading and one worth re-syncing."""
    from datetime import date as date_cls, timedelta as td

    from app.services.lever_engine import diagnose

    end = date_cls.today()
    result = diagnose(db, client_a, from_date=end - td(days=29), to_date=end)
    assert set(result.source_freshness) == set(result.readiness), (
        "freshness and readiness must describe the same four sources"
    )


def test_a_silent_lead_feed_does_not_silence_flat_credit_work(db, client_a):
    """The gate exists because a silent lead feed makes every lead estimate
    a fiction. That is an argument about estimates, not about every rule.

    SMA relaunched on 7 September 2026 and its custom GA4 events did not
    come with it. The gate fired and took 26 prompt actions down with it —
    work whose value is a flat credit and never read the missing number.
    """
    from app.services.decision_types import LeverFinding
    from app.models.decision import DiagnosticLayer, GrowthAction
    from app.services.lever_engine import survives_tracking_gate

    def _finding(**evidence) -> LeverFinding:
        return LeverFinding(
            rule_key="k" + str(sorted(evidence.items())),
            lever=GrowthAction.AI_VISIBILITY.value,
            stage=DiagnosticLayer.VISIBILITY,
            diagnosis="d",
            recommended_action="a",
            success_metric="m",
            evidence_json=dict(evidence),
            baseline_metrics_json={},
            impact=0.0,
            confidence=0.0,
            urgency=0.0,
            effort=0.0,
            priority_score=0.0,
        )

    prompt = _finding(rule_id="6")
    entity = _finding(rule_id="5a")
    crawlers = _finding(rule_id="ai_crawlers_unblock")
    conversion = _finding(rule_id="1b")
    ctr = _finding(rule_id="2a")

    assert survives_tracking_gate(prompt, set())
    assert survives_tracking_gate(entity, set())
    assert survives_tracking_gate(crawlers, set())
    # These two are a lead estimate, so a silent lead feed does make them
    # fiction and they stay suppressed.
    assert not survives_tracking_gate(conversion, set())
    assert not survives_tracking_gate(ctr, set())
