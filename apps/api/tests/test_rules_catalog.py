"""The catalogue cannot drift from the engine.

Growth actions are a limited budget, so the list of things competing for
them has to be reviewable — and a reference that quietly falls behind the
code is worse than none, because it is believed.
"""

from __future__ import annotations

from app.decisions.actions.value import (
    DEFAULT_MINUTES,
    GROWTH_ACTION_MAX_MINUTES,
    _minutes,
)
from app.decisions.thresholds import DEFAULT_DECISION_THRESHOLDS as LIMITS
from app.rules_catalog import CHECKS, _row, _signals_in_code
from app.services.lever_engine import ACTION_RULE_IDS


def test_every_check_the_engine_emits_is_described():
    missing = sorted(_signals_in_code() - set(CHECKS))
    assert missing == [], (
        "these checks ship without a description in app/rules_catalog.py: "
        + ", ".join(missing)
    )


def test_nothing_is_described_that_the_engine_no_longer_emits():
    """Catches a removed rule leaving its documentation, and its code,
    behind — which is how five deleted rules kept passing tests."""
    stale = sorted(set(CHECKS) - _signals_in_code())
    assert stale == [], "described but never emitted: " + ", ".join(stale)


def test_every_check_says_what_it_spends():
    for signal in CHECKS:
        assert _row(signal)["spends"] in {"core work", "growth action"}


def test_conversion_checks_are_not_core_work():
    """They were all marked as upkeep, because the technical predicate was
    asked about gates it knows nothing about."""
    for signal in ("tracking", "site_conversion", "converting_page_dropped"):
        assert _row(signal)["spends"] == "growth action"


def test_meta_descriptions_are_core_work_and_titles_are_not():
    """A title earns the click, so it competes for an action. A
    description is upkeep Google rewrites at will."""
    assert _row("description_missing")["spends"] == "core work"
    assert _row("title_missing")["spends"] == "growth action"


def test_blocking_checks_are_marked_as_preempting():
    assert _row("status_error")["blocking"] == "yes"
    assert _row("description_missing")["blocking"] == ""


def test_every_check_has_a_question_and_a_trigger():
    for signal, check in CHECKS.items():
        assert check["question"].endswith("?"), signal
        assert check["fires"].strip(), signal
        assert check["impact"].strip(), signal


def test_every_growth_action_fits_in_an_hour():
    """An action is a task someone does in an hour or less. A rule that
    takes longer is a project, and spending a client's monthly allowance
    on it misrepresents what they are buying."""
    for rule_id in sorted(set(ACTION_RULE_IDS.values()) | set(DEFAULT_MINUTES)):
        minutes = _minutes(rule_id, LIMITS)
        assert 0 < minutes <= GROWTH_ACTION_MAX_MINUTES, (
            f"{rule_id} is estimated at {minutes} minutes"
        )


def test_every_action_the_engine_can_emit_has_an_estimate():
    """Without one the rule silently inherits the hour cap, which reads as
    a measurement and is a default."""
    missing = sorted(set(ACTION_RULE_IDS.values()) - set(DEFAULT_MINUTES))
    assert missing == [], "no estimated_minutes for: " + ", ".join(missing)
