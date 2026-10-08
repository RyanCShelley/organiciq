"""Growth actions are counted in the unit of the outcome they move.

Actions were priced in expected leads a month until October 2026. That
required a site-wide lead rate to be applied to one page's clicks, and the
three rules with no clicks-to-leads model at all carried a flat credit
instead — so twenty-five tracked prompts arrived identically priced and the
ranking was really the tie-break underneath.
"""

from __future__ import annotations

import pytest

from app.decisions.actions.demand import (
    DEFAULT_MINUTES,
    DEMAND_UNIT,
    GROWTH_ACTION_MAX_MINUTES,
    PRECONDITION_RULES,
    demand_for,
    monthly_from_window,
)
from app.decisions.constraint import LADDER
from app.decisions.thresholds import merge_thresholds

LIMITS = merge_thresholds(None)


# ── The unit ──


def test_a_window_is_restated_per_month():
    """Windows are whatever Search Console could serve. Comparing a 28-day
    count with a 30-day one ranks by how much data arrived."""
    assert monthly_from_window(280, 28) == pytest.approx(300)
    assert monthly_from_window(300, 30) == pytest.approx(300)
    assert monthly_from_window(100, 0) == 0.0


def test_every_layer_names_what_it_counts():
    """A number on a card with no unit is a number nobody can argue with."""
    for layer in LADDER:
        assert DEMAND_UNIT[layer.value]


def test_each_layer_keeps_its_own_unit():
    searches = demand_for(
        "6", layer="visibility", thresholds=LIMITS, window_days=30,
        counted_monthly=74_000,
    )
    clicks = demand_for(
        "3a", layer="traffic", thresholds=LIMITS, window_days=30,
        counted_in_window=312,
    )
    sessions = demand_for(
        "1a", layer="conversion", thresholds=LIMITS, window_days=30,
        counted_in_window=402,
    )
    assert (searches.unit, clicks.unit, sessions.unit) == (
        "searches / mo", "clicks / mo", "sessions / mo",
    )
    # Nothing converts between them. 74,000 searches is not 74,000 of
    # anything else, and the engine never pretends otherwise.
    assert searches.demand == pytest.approx(74_000)
    assert clicks.demand == pytest.approx(312)
    assert sessions.demand == pytest.approx(402)


def test_a_monthly_count_passes_through_untouched():
    """Search volume is already per month; restating it would deflate it."""
    value = demand_for(
        "6", layer="visibility", thresholds=LIMITS, window_days=28,
        counted_monthly=1000,
    )
    assert value.demand == pytest.approx(1000)


def test_the_evidence_label_never_changes_the_count():
    """A reader can discount an estimate themselves. An engine that
    discounts it as well has discounted it twice."""
    measured = demand_for(
        "2a", layer="traffic", thresholds=LIMITS, window_days=30,
        counted_in_window=100, evidence_label="measured",
    )
    estimated = demand_for(
        "2a", layer="traffic", thresholds=LIMITS, window_days=30,
        counted_in_window=100, evidence_label="estimated",
    )
    assert measured.demand == estimated.demand
    assert measured.evidence_label != estimated.evidence_label


# ── No floor ──


def test_nothing_is_dropped_for_being_small():
    """A rule gates itself on its own inputs. A second, global floor in a
    unit the rule does not use was how a prompt with real demand got
    dropped for failing a lead conversion nobody asked for."""
    tiny = demand_for(
        "2a", layer="traffic", thresholds=LIMITS, window_days=30,
        counted_in_window=1,
    )
    assert tiny.demand > 0
    assert not tiny.precondition


# ── Preconditions ──


def test_a_precondition_carries_no_count():
    """An engine that cannot fetch the site will not cite any page on it,
    so it is not ranked against one page's demand."""
    for rule_id in PRECONDITION_RULES:
        value = demand_for(
            rule_id, layer="visibility", thresholds=LIMITS, window_days=30,
        )
        assert value.precondition
        assert value.demand == 0.0
        assert value.as_dict()["precondition"] is True


def test_a_rule_with_no_count_and_no_precondition_is_a_bug():
    with pytest.raises(ValueError, match="no count"):
        demand_for("1a", layer="conversion", thresholds=LIMITS, window_days=30)


# ── An hour or less ──


def test_every_action_fits_in_an_hour():
    """That is what makes it a growth action rather than a project."""
    for rule_id, minutes in DEFAULT_MINUTES.items():
        assert minutes <= GROWTH_ACTION_MAX_MINUTES, rule_id


def test_the_minutes_are_tunable_per_client():
    tuned = merge_thresholds({"estimated_minutes": {"1a": 20}})
    assert (
        demand_for(
            "1a", layer="conversion", thresholds=tuned, window_days=30,
            counted_in_window=100,
        ).estimated_minutes
        == 20
    )


def test_overriding_one_rules_minutes_keeps_the_others():
    """A per-rule map merged wholesale would silently delete every rule
    the override did not mention."""
    tuned = merge_thresholds({"estimated_minutes": {"1a": 20}})
    assert tuned["estimated_minutes"]["1a"] == 20
    assert tuned["estimated_minutes"]["2a"] == 30


# ── Every action rule says what it is about ──


def test_every_action_rule_counts_demand():
    """A rule that maps to an action id has to write a count.

    This is a static check because the alternative is a client whose data
    happens not to trigger the rule, and then the omission ships. An action
    with nothing to rank it by sorts last and disappears off the bottom of
    the ledger, which is the quietest possible failure.

    The engine's evidence dicts are literals, so the key that names the
    rule and the key that counts it sit in the same dict and can be read
    together.
    """
    import ast
    from pathlib import Path

    from app.services.lever_engine import ACTION_RULE_IDS

    source = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "lever_engine.py"
    ).read_text(encoding="utf-8")

    missing: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        literals = {
            key.value: value
            for key, value in zip(node.keys, node.values)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        rule_id = literals.get("rule_id")
        if isinstance(rule_id, ast.Constant) and isinstance(rule_id.value, str):
            rule = rule_id.value
        else:
            signal = literals.get("audit_signal") or literals.get("gate")
            if not (isinstance(signal, ast.Constant) and isinstance(signal.value, str)):
                continue
            rule = ACTION_RULE_IDS.get(signal.value, "")
        if not rule or rule not in set(ACTION_RULE_IDS.values()):
            continue
        if rule in PRECONDITION_RULES:
            continue
        if "demand_raw" not in literals and "demand_monthly" not in literals:
            missing.append(rule)

    assert sorted(set(missing)) == [], (
        "these action rules build evidence with no count, so the ledger has "
        "nothing to rank them by: " + ", ".join(sorted(set(missing)))
    )


def test_work_that_cannot_be_sized_says_so_rather_than_reporting_zero():
    """SE Ranking returns no volume on prompts, and where no tracked term is
    close enough to stand in there is no number to give.

    A zero would read as "nobody is asking this" and sort the prompt below
    work that genuinely has no audience. The prompt is still tracked and
    still uncited; it is only the size that is missing.
    """
    unknown = demand_for(
        "6", layer="visibility", thresholds=LIMITS, window_days=30,
        counted_monthly=0.0, known=False,
    )
    assert unknown.demand is None
    assert unknown.known is False
    assert unknown.as_dict()["demand"] is None
    # And it is not confused with a precondition, which has a reason to
    # carry no number.
    assert unknown.precondition is False
