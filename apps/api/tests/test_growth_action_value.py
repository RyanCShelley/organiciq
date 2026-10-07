"""A growth action is a small task, and leads are not worth the same
everywhere.

The engine ranked everything by share of the monthly lead goal, which is
the right axis for a month of content work and the wrong one for a
twenty-minute edit. On an AC company's site, where one job is five
figures, a page leaking 0.4 leads a period is several thousand pounds for
ten minutes' work — and the share-of-goal threshold scored it 5.9 and
dropped it.
"""

from __future__ import annotations

from app.decisions.effort import (
    GROWTH_ACTION_MAX_MINUTES,
    LARGE,
    MEDIUM,
    SMALL,
    is_small_task,
    minutes_for,
)
from app.decisions.thresholds import merge_thresholds
from app.models.decision import DiagnosticLayer, GrowthAction
from app.services.action_promotion import promote_findings
from app.services.decision_types import LeverFinding

LIMITS = merge_thresholds(None)


def _finding(**kwargs) -> LeverFinding:
    evidence = {
        "effort_class": kwargs.pop("size", SMALL),
        "estimated_value": kwargs.pop("value", None),
        "promotion_class": "actionable",
    }
    return LeverFinding(
        rule_key="k",
        lever=GrowthAction.CONVERSION_PATH.value,
        stage=DiagnosticLayer.CONVERSION,
        diagnosis="d",
        recommended_action="a",
        success_metric="m",
        evidence_json=evidence,
        baseline_metrics_json={},
        impact=kwargs.pop("impact", 5.9),
        confidence=70,
        urgency=65,
        effort=40,
        priority_score=5.9,
        page_url="https://x/blog/post",
    )


def _promote(finding: LeverFinding):
    _, recommended = promote_findings(
        [finding], classifications={}, page_contexts={}, thresholds=LIMITS
    )
    return recommended


# ── Effort in minutes ──


def test_a_growth_action_is_an_hour_or_less():
    assert is_small_task(SMALL)
    assert not is_small_task(MEDIUM)
    assert not is_small_task(LARGE)
    assert minutes_for(SMALL) <= GROWTH_ACTION_MAX_MINUTES


# ── The second promotion route ──


def test_a_cheap_task_worth_real_money_promotes():
    """Ten minutes for four thousand pounds is worth doing whatever share
    of the monthly goal it represents."""
    assert _promote(_finding(size=SMALL, value=4000.0, impact=5.9))


def test_the_same_task_worth_nothing_does_not():
    assert _promote(_finding(size=SMALL, value=40.0, impact=5.9)) == []


def test_a_valuable_task_that_takes_a_month_does_not():
    """It is worth doing; it is not a growth action. Those are the small
    wins, and a project belongs in the plan."""
    assert _promote(_finding(size=LARGE, value=40000.0, impact=5.9)) == []


def test_without_a_lead_value_the_route_stays_shut():
    """Unknown value is not zero value, but it is not a licence to promote
    either — the engine falls back to counting leads."""
    assert _promote(_finding(size=SMALL, value=None, impact=5.9)) == []


def test_the_ordinary_route_still_works():
    assert _promote(_finding(size=LARGE, value=None, impact=60.0))


def test_value_at_exactly_the_bar_promotes():
    assert _promote(_finding(size=SMALL, value=250.0, impact=1.0))
    assert _promote(_finding(size=SMALL, value=249.0, impact=1.0)) == []
