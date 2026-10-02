"""The 3x override rule.

From the product spec: "if our team overrides the same rule's suggestion three
times, the rule is a bad fit — it gets rewritten or removed." This is the
mechanism that stops the queue re-accumulating the noise it was cleared of.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from app.models.decision import (
    Decision,
    DecisionPriority,
    DecisionStatus,
    DecisionType,
    DiagnosticLayer,
    GrowthAction,
)
from app.services.action_promotion import promote_findings
from app.services.decision_types import LeverFinding
from app.services.lever_engine import (
    OVERRIDE_RETIREMENT_COUNT,
    _overridden_rule_families,
    rule_family,
)

END = date(2026, 8, 31)
START = END - timedelta(days=29)


def _dismissed(db, client_id, *, rule_key, lever, evidence, window=0):
    db.add(
        Decision(
            id=uuid4(),
            client_id=client_id,
            rule_key=rule_key,
            decision_type=DecisionType.BOTTLENECK,
            date_range_start=START - timedelta(days=30 * window),
            date_range_end=END - timedelta(days=30 * window),
            growth_action=lever,
            diagnostic_layer=DiagnosticLayer.VISIBILITY,
            diagnosis="x",
            recommended_action="y",
            success_metric="z",
            priority=DecisionPriority.MEDIUM,
            priority_score=50,
            status=DecisionStatus.DISMISSED,
            evidence_json=evidence,
        )
    )


# --- What counts as "the same rule" ----------------------------------------


def test_the_family_is_the_kind_of_suggestion_not_the_page():
    assert rule_family("technical_seo", {"audit_signal": "missing_meta"}) == (
        "technical_seo:missing_meta"
    )
    assert rule_family("conversion_path", {"gate": "tracking"}) == "conversion_path:tracking"
    assert rule_family("internal_linking", {}) == "internal_linking"


def test_two_signals_on_one_lever_are_different_rules():
    """Retiring all of Technical SEO because metas were rejected would be wrong."""
    meta = rule_family("technical_seo", {"audit_signal": "missing_meta"})
    status = rule_family("technical_seo", {"audit_signal": "status_error"})

    assert meta != status


# --- Counting ---------------------------------------------------------------


def test_three_dismissals_across_pages_retire_the_rule(db, client_a):
    for index in range(3):
        _dismissed(
            db,
            client_a.id,
            rule_key=f"key-{index}",
            lever=GrowthAction.TECHNICAL_SEO,
            evidence={"rule_family": "technical_seo:missing_meta", "audit_signal": "missing_meta"},
        )
    db.commit()

    counts = _overridden_rule_families(db, client_a.id)

    assert counts["technical_seo:missing_meta"] == OVERRIDE_RETIREMENT_COUNT


def test_the_same_page_dismissed_repeatedly_is_one_disagreement(db, client_a):
    """Three months of declining the same page is a decision about that page."""
    for month in range(3):
        _dismissed(
            db,
            client_a.id,
            rule_key="same-key",
            lever=GrowthAction.TECHNICAL_SEO,
            evidence={"audit_signal": "missing_meta"},
            window=month,
        )
    db.commit()

    counts = _overridden_rule_families(db, client_a.id)

    assert counts["technical_seo:missing_meta"] == 1


def test_dismissals_of_different_rules_do_not_add_up(db, client_a):
    _dismissed(
        db,
        client_a.id,
        rule_key="a",
        lever=GrowthAction.TECHNICAL_SEO,
        evidence={"audit_signal": "missing_meta"},
    )
    _dismissed(
        db,
        client_a.id,
        rule_key="b",
        lever=GrowthAction.INTERNAL_LINKING,
        evidence={},
    )
    db.commit()

    counts = _overridden_rule_families(db, client_a.id)

    assert counts == {"technical_seo:missing_meta": 1, "internal_linking": 1}


# --- What it does to the queue ---------------------------------------------


def _finding(**over):
    base = dict(
        rule_key="k",
        lever="technical_seo",
        stage=DiagnosticLayer.VISIBILITY,
        diagnosis="Missing core meta",
        recommended_action="Write a title",
        success_metric="",
        evidence_json={"promotion_class": "actionable", "rule_family": "technical_seo:missing_meta"},
        baseline_metrics_json={},
        impact=99.0,
        confidence=90.0,
        urgency=90.0,
        effort=10.0,
        priority_score=95.0,
    )
    base.update(over)
    return LeverFinding(**base)


def test_a_retired_rule_stops_spending_actions():
    finding = _finding(override_count=3)

    all_findings, recommended = promote_findings(
        [finding], classifications={}, page_contexts={}, thresholds={}
    )

    assert recommended == []
    assert "rewrite or retire this rule" in all_findings[0].promotion_blocked_reason


def test_a_retired_rule_still_appears():
    """A rule that vanishes silently can never be rewritten or deliberately removed."""
    finding = _finding(override_count=4)

    all_findings, _ = promote_findings(
        [finding], classifications={}, page_contexts={}, thresholds={}
    )

    assert len(all_findings) == 1
    assert all_findings[0].override_count == 4


def test_two_dismissals_are_not_yet_a_verdict():
    """Asserted on the reason, not on promotion: other gates block this
    synthetic finding for reasons of their own, and the question here is only
    whether the override rule has fired."""
    finding = _finding(override_count=2)

    all_findings, _ = promote_findings(
        [finding], classifications={}, page_contexts={}, thresholds={}
    )

    assert "retire this rule" not in (all_findings[0].promotion_blocked_reason or "")


# --- T8: reasons, and a rule getting another chance -------------------------


def test_a_dismissal_needs_a_reason_from_the_list(db, client_a):
    """Free text meant the override rule counted disagreements it could not read."""
    import pytest

    from app.models.decision import DismissalReason
    from app.services.decisions import update_decision_status

    _dismissed(
        db,
        client_a.id,
        rule_key="k",
        lever=GrowthAction.TECHNICAL_SEO,
        evidence={"audit_signal": "missing_meta"},
    )
    db.commit()
    decision = db.query(Decision).filter(Decision.client_id == client_a.id).one()

    with pytest.raises(ValueError, match="dismissal_reason must be one of"):
        update_decision_status(
            db,
            client_id=client_a.id,
            decision_id=decision.id,
            status=DecisionStatus.DISMISSED,
            dismissal_reason="because",
        )

    updated = update_decision_status(
        db,
        client_id=client_a.id,
        decision_id=decision.id,
        status=DecisionStatus.DISMISSED,
        dismissal_reason=DismissalReason.NOT_RELEVANT.value,
    )
    assert updated.dismissal_reason == "not_relevant"


def test_a_bug_report_is_not_a_vote_against_the_rule(db, client_a):
    """"Wrong data" and "already done" say nothing about whether the rule fits,
    and counting them retires rules for being right at a bad moment."""
    for index, reason in enumerate(("wrong_data", "already_done", "not_relevant")):
        _dismissed(
            db,
            client_a.id,
            rule_key=f"k{index}",
            lever=GrowthAction.TECHNICAL_SEO,
            evidence={"audit_signal": "missing_meta"},
        )
        db.flush()
        db.query(Decision).filter(Decision.rule_key == f"k{index}").update(
            {"dismissal_reason": reason}
        )
    db.commit()

    counts = _overridden_rule_families(db, client_a.id)

    assert counts.get("technical_seo:missing_meta") == 1


def test_old_dismissals_stop_counting(db, client_a):
    """A judgement made against last quarter's site is not about this one."""
    for index in range(3):
        _dismissed(
            db,
            client_a.id,
            rule_key=f"old{index}",
            lever=GrowthAction.TECHNICAL_SEO,
            evidence={"audit_signal": "missing_meta"},
            window=8,  # roughly eight months back
        )
    db.commit()

    assert _overridden_rule_families(db, client_a.id, reset_days=90) == {}
    # And with a longer memory they count again.
    assert _overridden_rule_families(db, client_a.id, reset_days=400)[
        "technical_seo:missing_meta"
    ] == 3


def test_changing_the_thresholds_gives_a_rule_another_chance(db, client_a):
    """The rule that was dismissed is not the rule running now."""
    from app.services.decisions import upsert_thresholds

    for index in range(3):
        _dismissed(
            db,
            client_a.id,
            rule_key=f"k{index}",
            lever=GrowthAction.TECHNICAL_SEO,
            evidence={"audit_signal": "missing_meta"},
        )
    db.commit()
    assert _overridden_rule_families(db, client_a.id)["technical_seo:missing_meta"] == 3

    upsert_thresholds(db, client_a.id, {"minimum_actionable_impact": 30})

    assert _overridden_rule_families(db, client_a.id) == {}
