"""Growth actions are valued in expected leads per month.

The old scale was a share of the monthly goal, capped at a hundred,
discounted by an evidence tier and then weighed against urgency and
effort — four transformations between "this page would produce 0.6 more
leads" and the number on the card, and the card's number could not be read
back as leads by anyone.
"""

from __future__ import annotations

import pytest

from app.decisions.actions.value import (
    DEFAULT_MINUTES,
    GROWTH_ACTION_MAX_MINUTES,
    monthly_from_window,
    value_for,
)
from app.decisions.thresholds import merge_thresholds

LIMITS = merge_thresholds(None)


# ── The unit ──


def test_a_window_is_restated_per_month():
    """Windows are whatever Search Console could serve. Comparing a 28-day
    estimate with a 30-day one ranks by how much data arrived."""
    assert monthly_from_window(0.56, 28) == pytest.approx(0.6)
    assert monthly_from_window(0.6, 30) == pytest.approx(0.6)
    assert monthly_from_window(1.0, 0) == 0.0


def test_the_raw_estimate_is_not_scaled_by_a_goal_or_a_tier():
    """It is the number the rule already computed, restated per month."""
    value = value_for("1a", thresholds=LIMITS, window_days=30, raw_leads_for_window=0.6)
    assert value.expected_leads_monthly == pytest.approx(0.6)
    assert value.raw_monthly_leads == pytest.approx(0.6)
    assert value.value_basis == "estimated_incremental_leads"


def test_the_evidence_label_never_changes_the_number():
    """A reader can discount an estimate themselves. An engine that
    discounts it as well is lying quietly."""
    measured = value_for(
        "1a", thresholds=LIMITS, window_days=30, raw_leads_for_window=0.6,
        evidence_label="measured",
    )
    estimated = value_for(
        "1a", thresholds=LIMITS, window_days=30, raw_leads_for_window=0.6,
        evidence_label="estimated",
    )
    assert measured.expected_leads_monthly == estimated.expected_leads_monthly
    assert measured.evidence_label != estimated.evidence_label


def test_the_reliability_prior_multiplies():
    tuned = merge_thresholds({"reliability_1a": 0.5})
    value = value_for("1a", thresholds=tuned, window_days=30, raw_leads_for_window=0.6)
    assert value.expected_leads_monthly == pytest.approx(0.3)
    assert value.reliability_prior == 0.5


# ── The floor ──


def test_nothing_is_dropped_for_being_small():
    """36 leads to 37 is worth doing."""
    assert value_for(
        "1a", thresholds=LIMITS, window_days=30, raw_leads_for_window=0.2
    ).above_floor


def test_below_a_tenth_of_a_lead_a_month_falls_away():
    assert not value_for(
        "1a", thresholds=LIMITS, window_days=30, raw_leads_for_window=0.05
    ).above_floor


def test_exactly_at_the_floor_stays():
    assert value_for(
        "1a", thresholds=LIMITS, window_days=30, raw_leads_for_window=0.1
    ).above_floor


def test_a_bigger_action_outranks_a_smaller_one():
    bigger = value_for("1a", thresholds=LIMITS, window_days=30, raw_leads_for_window=0.4)
    smaller = value_for("1b", thresholds=LIMITS, window_days=30, raw_leads_for_window=0.3)
    assert bigger.expected_leads_monthly > smaller.expected_leads_monthly


# ── Flat credit ──


def test_flat_credit_actions_say_so():
    value = value_for("6", thresholds=LIMITS, window_days=28)
    assert value.value_basis == "flat_credit"
    assert value.expected_leads_monthly == pytest.approx(0.3)


def test_a_rule_with_neither_an_estimate_nor_a_credit_is_a_bug():
    with pytest.raises(ValueError, match="no raw lead estimate"):
        value_for("1a", thresholds=LIMITS, window_days=30)


# ── An hour or less ──


def test_every_action_fits_in_an_hour():
    """That is what makes it a growth action rather than a project."""
    for rule_id, minutes in DEFAULT_MINUTES.items():
        assert minutes <= GROWTH_ACTION_MAX_MINUTES, rule_id


def test_the_minutes_are_tunable_per_client():
    tuned = merge_thresholds({"estimated_minutes": {"1a": 20}})
    assert (
        value_for(
            "1a", thresholds=tuned, window_days=30, raw_leads_for_window=0.6
        ).estimated_minutes
        == 20
    )


def test_overriding_one_rules_minutes_keeps_the_others():
    """A per-rule map merged wholesale would silently delete every rule
    the override did not mention."""
    tuned = merge_thresholds({"estimated_minutes": {"1a": 20}})
    assert tuned["estimated_minutes"]["1a"] == 20
    assert tuned["estimated_minutes"]["2a"] == 30
