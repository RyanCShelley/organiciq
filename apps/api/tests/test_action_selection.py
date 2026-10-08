"""Which findings can spend a growth action, and in what order."""

from __future__ import annotations

from app.decisions.thresholds import merge_thresholds
from app.models.decision import DiagnosticLayer, GrowthAction
from app.services.decision_types import LeverFinding
from app.services.lever_engine import action_rule_id, measure_demand

LIMITS = merge_thresholds(None)


def _finding(**kwargs) -> LeverFinding:
    evidence = {"promotion_class": "actionable"}
    evidence.update(kwargs.pop("evidence", {}))
    lever = kwargs.pop("lever", GrowthAction.CONVERSION_PATH.value)
    return LeverFinding(
        rule_key=kwargs.pop("key", "k"),
        lever=lever,
        stage=(
            DiagnosticLayer.CONVERSION
            if lever == GrowthAction.CONVERSION_PATH.value
            else DiagnosticLayer.TRAFFIC
        ),
        diagnosis="d",
        recommended_action="a",
        success_metric="m",
        evidence_json=evidence,
        baseline_metrics_json={},
        impact=kwargs.pop("impact", 10.0),
        confidence=70,
        urgency=65,
        effort=40,
        priority_score=kwargs.pop("score", 10.0),
        page_url=kwargs.pop("page_url", None),
    )


def test_only_the_named_actions_can_spend_one():
    assert action_rule_id(_finding(evidence={"rule_id": "1a"})) == "1a"
    assert action_rule_id(_finding(evidence={"gate": "rank_push"})) == "2c"
    assert action_rule_id(_finding(evidence={"audit_signal": "prompt_not_cited"})) == "6"
    # Recurring work the plan already covers.
    assert action_rule_id(_finding(evidence={"audit_signal": "description_missing"})) is None
    assert action_rule_id(_finding(evidence={"gate": "tracking"})) is None


def test_report_only_findings_never_become_actions():
    out = measure_demand(
        [_finding(evidence={"audit_signal": "description_missing"})],
        thresholds=LIMITS,
        window_days=30,
    )
    assert out[0].is_recommended_action is False
    assert "demand" not in out[0].evidence_json


def test_an_action_is_counted_in_its_layers_unit():
    """A conversion action is about the people who arrive on the page."""
    out = measure_demand(
        [_finding(evidence={"rule_id": "1a", "demand_raw": 280})],
        thresholds=LIMITS,
        window_days=28,
    )
    assert out[0].evidence_json["demand"] == 300.0
    assert out[0].evidence_json["demand_unit"] == "sessions / mo"
    assert out[0].evidence_json["estimated_minutes"] == 45


def test_nothing_is_dropped_for_being_small():
    """There is no floor. A rule gates itself on its own inputs, and a
    second global floor in a unit the rule does not use is how an action
    with real demand got dropped for failing a lead conversion."""
    out = measure_demand(
        [_finding(evidence={"rule_id": "1a", "demand_raw": 2})],
        thresholds=LIMITS,
        window_days=30,
    )
    assert out[0].evidence_json["demand"] == 2.0
    assert "below_floor" not in out[0].evidence_json
    assert out[0].promotion_blocked_reason is None


def test_actions_are_ranked_by_how_many_people_they_are_about():
    findings = [
        _finding(key="small", evidence={"rule_id": "1b", "demand_raw": 30}),
        _finding(key="big", evidence={"rule_id": "1a", "demand_raw": 900}),
    ]
    out = measure_demand(findings, thresholds=LIMITS, window_days=30)
    assert [f.rule_key for f in out] == ["big", "small"]


def test_a_precondition_outranks_every_count():
    """A blocked crawler holds back every page under it, so it is not
    ranked against one page's demand."""
    findings = [
        _finding(key="big", evidence={"rule_id": "1a", "demand_raw": 9000}),
        _finding(key="blocked", evidence={"audit_signal": "ai_crawlers_blocked"}),
    ]
    out = measure_demand(findings, thresholds=LIMITS, window_days=30)
    assert [f.rule_key for f in out] == ["blocked", "big"]
    assert out[0].evidence_json["precondition"] is True


def test_a_monthly_count_is_not_restated():
    """Search volume is already per month. Restating it would deflate it
    by the ratio of the window to thirty days."""
    out = measure_demand(
        [_finding(evidence={"audit_signal": "prompt_not_cited", "demand_monthly": 74000})],
        thresholds=LIMITS,
        window_days=28,
    )
    assert out[0].evidence_json["demand"] == 74000.0


def test_an_action_rule_with_no_count_is_reported_as_a_bug():
    """Silently ranking it last would bury it. No client input can cause
    this — a rule that forgets to say what it is about causes it."""
    out = measure_demand(
        [_finding(evidence={"rule_id": "2a"})],
        thresholds=LIMITS,
        window_days=30,
    )
    assert out[0].evidence_json["demand_error"] == "no_count"
    assert out[0].is_recommended_action is False


def test_a_page_with_work_settling_is_not_recommended_again():
    """Recommending the same page a fortnight after someone rewrote it
    asks them to do it twice."""
    out = measure_demand(
        [
            _finding(
                evidence={"rule_id": "1a", "demand_raw": 402},
                page_url="https://x/done",
            )
        ],
        thresholds=LIMITS,
        window_days=30,
        settling={"https://x/done"},
    )
    assert out[0].is_recommended_action is False
    assert out[0].promotion_blocked_reason == "settling"
    assert out[0].evidence_json["settling"] is True


def test_a_page_booked_for_refresh_keeps_its_steps_and_stops_counting():
    """The work is paid for out of the content allowance. Spending a growth
    action on it would charge the client twice for one job."""
    out = measure_demand(
        [
            _finding(
                evidence={"rule_id": "1b", "demand_raw": 402},
                page_url="https://x/booked",
            )
        ],
        thresholds=LIMITS,
        window_days=30,
        refreshing={"https://x/booked"},
    )
    assert out[0].is_recommended_action is False
    assert out[0].evidence_json["folded_into_refresh"] is True
    # It is still a finding: someone needs to know it is on the list.
    assert out[0].recommended_action


def test_an_untouched_page_is_unaffected():
    out = measure_demand(
        [
            _finding(
                evidence={"rule_id": "1a", "demand_raw": 402},
                page_url="https://x/fresh",
            )
        ],
        thresholds=LIMITS,
        window_days=30,
        settling={"https://x/other"},
        refreshing={"https://x/another"},
    )
    assert "settling" not in out[0].evidence_json
    assert "folded_into_refresh" not in out[0].evidence_json


def test_sessions_are_restated_on_ga4s_window_not_search_consoles():
    """The two sources rarely cover the same days.

    SMA's Search Console had sixteen days in the period and GA4 had thirty.
    Restating a GA4 session count on the Search Console window turned 100
    sessions into 187.5 a month, on the same card whose diagnosis read
    "100 sessions and no conversions".
    """
    out = measure_demand(
        [
            _finding(evidence={"rule_id": "1a", "demand_raw": 100}),
            _finding(
                key="search",
                lever=GrowthAction.SERP_CTR.value,
                evidence={"rule_id": "2a", "demand_raw": 160},
            ),
        ],
        thresholds=LIMITS,
        window_days=16,
        session_window_days=30,
    )
    by_rule = {f.evidence_json["rule_id"]: f.evidence_json["demand"] for f in out}
    assert by_rule["1a"] == 100.0, "sessions covered thirty days already"
    assert by_rule["2a"] == 300.0, "clicks covered sixteen and are restated"


def test_one_window_still_works_when_only_one_is_known():
    out = measure_demand(
        [_finding(evidence={"rule_id": "1a", "demand_raw": 100})],
        thresholds=LIMITS,
        window_days=30,
    )
    assert out[0].evidence_json["demand"] == 100.0
