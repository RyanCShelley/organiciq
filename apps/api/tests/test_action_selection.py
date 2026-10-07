"""Which findings can spend a growth action, and in what order."""

from __future__ import annotations

from app.decisions.thresholds import merge_thresholds
from app.models.decision import DiagnosticLayer, GrowthAction
from app.services.decision_types import LeverFinding
from app.services.lever_engine import action_rule_id, value_actions

LIMITS = merge_thresholds(None)


def _finding(**kwargs) -> LeverFinding:
    evidence = {"promotion_class": "actionable"}
    evidence.update(kwargs.pop("evidence", {}))
    return LeverFinding(
        rule_key=kwargs.pop("key", "k"),
        lever=kwargs.pop("lever", GrowthAction.CONVERSION_PATH.value),
        stage=DiagnosticLayer.CONVERSION,
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
    out = value_actions(
        [_finding(evidence={"audit_signal": "description_missing"})],
        thresholds=LIMITS,
        window_days=30,
    )
    assert out[0].is_recommended_action is False
    assert "expected_leads_monthly" not in out[0].evidence_json


def test_an_action_is_valued_in_leads_per_month():
    out = value_actions(
        [_finding(evidence={"rule_id": "1a", "estimated_incremental_leads": 0.56})],
        thresholds=LIMITS,
        window_days=28,
    )
    assert out[0].evidence_json["expected_leads_monthly"] == 0.6
    assert out[0].evidence_json["value_basis"] == "estimated_incremental_leads"
    assert out[0].evidence_json["estimated_minutes"] == 45


def test_a_tiny_action_is_recorded_rather_than_hidden():
    out = value_actions(
        [_finding(evidence={"rule_id": "1a", "estimated_incremental_leads": 0.02})],
        thresholds=LIMITS,
        window_days=30,
    )
    assert out[0].evidence_json["below_floor"] is True
    assert out[0].is_recommended_action is False
    assert out[0].promotion_blocked_reason == "below_floor"


def test_actions_are_ranked_by_what_they_are_worth():
    findings = [
        _finding(key="small", evidence={"rule_id": "1b", "estimated_incremental_leads": 0.3}),
        _finding(key="big", evidence={"rule_id": "1a", "estimated_incremental_leads": 0.9}),
    ]
    out = value_actions(findings, thresholds=LIMITS, window_days=30)
    assert [f.rule_key for f in out] == ["big", "small"]


def test_a_flat_credit_action_needs_no_estimate():
    out = value_actions(
        [_finding(evidence={"audit_signal": "prompt_not_cited"})],
        thresholds=LIMITS,
        window_days=30,
    )
    assert out[0].evidence_json["value_basis"] == "flat_credit"
    assert out[0].evidence_json["expected_leads_monthly"] == 0.3


def test_an_action_with_no_estimate_and_no_credit_is_flagged_not_zeroed():
    """Silently valuing it at nothing would bury a bug."""
    out = value_actions(
        [_finding(evidence={"rule_id": "2a"})], thresholds=LIMITS, window_days=30
    )
    assert out[0].evidence_json["value_error"] == "no_raw_lead_estimate"
    assert out[0].is_recommended_action is False
