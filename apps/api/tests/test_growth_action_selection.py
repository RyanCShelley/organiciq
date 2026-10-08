"""What counts as a growth action is decided once.

It was decided twice. `app.action_plan` filtered `findings` by the
growth-action predicate; the web read `recommended_actions`, which is the
older impact-and-confidence promotion and carries report-only work that was
never valued in leads.

So the screen listed "Tracked keyword is not ranking" eight times, every
row showing an em dash for leads and for time, while the command used to
verify the very same client printed three real actions with real numbers.
The two never had to agree, so they didn't — and the CLI being right is
what hid it, because the CLI was what got checked.
"""

from __future__ import annotations

from app.models.decision import DiagnosticLayer
from app.services.decision_types import LeverFinding
from app.services.lever_engine import (
    ACTION_RULE_IDS,
    action_rule_id,
    below_floor_actions,
    growth_actions,
    unvalued_actions,
)


def _finding(**evidence) -> LeverFinding:
    return LeverFinding(
        rule_key="k" + str(abs(hash(tuple(sorted(evidence.items()))))),
        lever="conversion_path",
        stage=DiagnosticLayer.CONVERSION,
        diagnosis="d",
        recommended_action="a",
        success_metric="m",
        evidence_json=dict(evidence),
        baseline_metrics_json={},
        impact=10.0,
        confidence=50.0,
        urgency=50.0,
        effort=50.0,
        priority_score=10.0,
    )


def test_only_a_rule_that_can_spend_an_action_is_one():
    """A keyword finding has no rule id, so it reports and never competes.
    Eight of them filled the screen."""
    keyword = _finding(audit_signal="keyword_not_ranking")
    assert action_rule_id(keyword) is None
    assert growth_actions([keyword]) == []


def test_a_valued_action_is_offered():
    action = _finding(rule_id="1b", expected_leads_monthly=1.07)
    assert growth_actions([action]) == [action]


def test_below_the_floor_is_not_offered_but_is_kept():
    weak = _finding(rule_id="1b", expected_leads_monthly=0.01, below_floor=True)
    assert growth_actions([weak]) == []
    assert below_floor_actions([weak]) == [weak]


def test_an_action_the_valuer_could_not_price_is_surfaced_not_offered():
    broken = _finding(rule_id="1b", value_error="no raw lead estimate")
    assert growth_actions([broken]) == []
    assert unvalued_actions([broken]) == [broken]


def test_the_order_is_by_expected_leads():
    small = _finding(rule_id="6", expected_leads_monthly=0.15)
    big = _finding(rule_id="1b", expected_leads_monthly=2.04)
    assert growth_actions([small, big]) == [big, small]


def test_a_flat_credit_tie_is_broken_by_volume():
    """Every prompt carries the same credit by definition, so without this
    the top five of twenty is whichever order the database returned."""
    quiet = _finding(rule_id="6", expected_leads_monthly=0.15, tiebreak_volume=50)
    loud = _finding(rule_id="6", expected_leads_monthly=0.15, tiebreak_volume=74000)
    assert growth_actions([quiet, loud]) == [loud, quiet]


def test_every_offered_action_carries_what_the_screen_prints():
    """The row shows leads a month and minutes. A row that has neither is
    the bug this file exists for, and it renders as two em dashes."""
    offered = growth_actions(
        [
            _finding(rule_id="1b", expected_leads_monthly=1.07, estimated_minutes=15),
            _finding(audit_signal="keyword_not_ranking"),
        ]
    )
    assert len(offered) == 1
    for action in offered:
        assert action.evidence_json.get("expected_leads_monthly") is not None
        assert action.evidence_json.get("estimated_minutes") is not None


def test_the_catalogue_of_action_rules_is_not_empty():
    """If this ever empties, every client's plan silently goes to zero."""
    assert ACTION_RULE_IDS, "no signal maps to a growth action"


# ── Policy the old promotion carried, which the new selection must too ──


def test_a_suppressed_finding_is_not_an_action():
    """A gate failing means this finding's inputs cannot be trusted. The
    old promotion refused it; the new selection has to as well, or a
    failure upstream becomes an hour of someone's work."""
    finding = _finding(rule_id="1b", expected_leads_monthly=2.0)
    finding.suppressed_by = "tracking_silent"
    assert growth_actions([finding]) == []


def test_a_rule_this_team_has_dismissed_three_times_does_not_return():
    """Dismissed across three different pages and the rule is contested.
    Offering it again spends an action on an argument already had."""
    finding = _finding(rule_id="1b", expected_leads_monthly=2.0)
    finding.override_count = 3
    assert growth_actions([finding]) == []


def test_core_work_never_spends_an_action():
    """It is in the plan every month. Promoting it bills a client for work
    they already pay for."""
    finding = _finding(rule_id="2a", expected_leads_monthly=2.0)
    finding.core_work = True
    assert growth_actions([finding]) == []


def test_two_dismissals_is_not_yet_contested():
    finding = _finding(rule_id="1b", expected_leads_monthly=2.0)
    finding.override_count = 2
    assert growth_actions([finding]) == [finding]


# ── An empty plan has to say why ──


def test_what_is_suppressing_the_plan_is_named():
    """SMA's conversion tracking went silent after the site rebuild and 26
    actions correctly vanished with it. Showing nothing and not saying why
    reads as a broken tool rather than a broken tag."""
    from app.services.lever_engine import blocking_findings

    gate = _finding(gate="tracking")
    gate.diagnosis = "No conversions recorded in 14 days while 402 sessions arrived"
    blocked = _finding(rule_id="6", expected_leads_monthly=0.15)
    blocked.suppressed_by = gate.rule_key

    assert growth_actions([gate, blocked]) == []
    assert blocking_findings([gate, blocked]) == [gate]


def test_nothing_is_named_when_nothing_is_blocked():
    action = _finding(rule_id="1b", expected_leads_monthly=1.0)
    assert blocking_findings_of([action]) == []


def blocking_findings_of(findings):
    from app.services.lever_engine import blocking_findings

    return blocking_findings(findings)
