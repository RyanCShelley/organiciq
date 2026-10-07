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
