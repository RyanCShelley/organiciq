"""The goal in force now, rather than the twelve-month target.

Aquaman's twelve-month target is 50. Judging a thirty-day review against 50 in
month one makes an on-track client look like a failing one, and "that is next
September's number" is no answer to a client asking why they are missing.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services.lead_goals import current_lead_goal, goal_schedule, months_elapsed

ANCHOR = date(2026, 1, 1)

# The curve Aquaman is on: a 36-lead baseline reaching 50 in a year.
CHECKPOINTS = [
    {"label": "Today", "month": 0, "monthly_leads": 36.0},
    {"label": "3 months", "month": 3, "monthly_leads": 38.1},
    {"label": "6 months", "month": 6, "monthly_leads": 38.7},
    {"label": "9 months", "month": 9, "monthly_leads": 44.0},
    {"label": "12 months", "month": 12, "monthly_leads": 50.0},
]


def _client(**kwargs):
    base = dict(
        baseline_as_of=ANCHOR,
        baseline_period_end=ANCHOR,
        baseline_projection_json={"baseline_as_of": ANCHOR.isoformat(), "checkpoints": CHECKPOINTS},
        monthly_lead_goal=50,
        lead_goal_overrides={},
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


@pytest.mark.parametrize(
    "days_in,expected",
    [
        (0, 38),      # day one: aiming at the three-month checkpoint
        (30, 38),
        (89, 38),
        (95, 39),     # past three months: now aiming at six
        (180, 39),    # 5.9 months in — still short of six, so six is the target
        (190, 44),    # past six: aiming at nine
        (280, 50),    # past nine: aiming at twelve
        (400, 50),    # past the plan: the last checkpoint holds
    ],
)
def test_the_goal_is_the_next_checkpoint_ahead(days_in, expected):
    goal, checkpoint = current_lead_goal(_client(), ANCHOR + timedelta(days=days_in))

    assert goal == expected
    assert checkpoint is not None


def test_the_twelve_month_target_is_not_the_goal_on_day_one():
    """The whole point: 50 is next September's number."""
    goal, _ = current_lead_goal(_client(), ANCHOR)

    assert goal == 38
    assert goal != 50


def test_month_zero_is_never_the_goal():
    """Month zero is the baseline — where the client started, not a target."""
    schedule = goal_schedule(_client(), ANCHOR)

    assert schedule[0].month == 0
    assert schedule[0].current is False


def test_an_override_replaces_the_projected_goal():
    client = _client(lead_goal_overrides={"3": 42})

    goal, checkpoint = current_lead_goal(client, ANCHOR)

    assert goal == 42
    assert checkpoint.overridden is True
    assert checkpoint.projected == 38


def test_an_override_on_a_checkpoint_not_yet_reached_does_not_apply_early():
    client = _client(lead_goal_overrides={"12": 99})

    goal, _ = current_lead_goal(client, ANCHOR)

    assert goal == 38


def test_a_client_without_a_projection_falls_back_to_its_flat_goal():
    client = _client(baseline_projection_json=None, monthly_lead_goal=25)

    goal, checkpoint = current_lead_goal(client)

    assert goal == 25
    assert checkpoint is None


def test_no_projection_and_no_flat_goal_means_no_goal():
    client = _client(baseline_projection_json=None, monthly_lead_goal=None)

    assert current_lead_goal(client) == (None, None)


def test_a_checkpoint_carries_the_date_it_falls_due():
    schedule = {row.month: row for row in goal_schedule(_client(), ANCHOR)}

    # Three months is 91 days on a 365/12 month, not a calendar quarter.
    assert schedule[3].due == date(2026, 4, 2)
    assert schedule[12].due == date(2027, 1, 1)


def test_elapsed_months_are_measured_from_the_baseline():
    assert months_elapsed(_client(), ANCHOR) == 0.0
    assert round(months_elapsed(_client(), ANCHOR + timedelta(days=365)) or 0) == 12


def test_a_date_before_the_baseline_does_not_go_negative():
    assert months_elapsed(_client(), ANCHOR - timedelta(days=30)) == 0.0


def test_a_junk_override_is_ignored_rather_than_crashing():
    for bad in ({"3": "nonsense"}, {"3": 0}, {"3": -5}, {"3": None}, "not-a-dict"):
        goal, _ = current_lead_goal(_client(lead_goal_overrides=bad), ANCHOR)
        assert goal == 38, bad


# --- Through the API --------------------------------------------------------


def test_an_override_survives_re_running_the_projection(db, client_a):
    """The correction is deliberate; regenerating the curve must not discard it."""
    from app.services.clients import update_client
    from app.schemas import ClientUpdate

    client_a.baseline_as_of = ANCHOR
    client_a.baseline_period_end = ANCHOR
    client_a.baseline_projection_json = {
        "baseline_as_of": ANCHOR.isoformat(),
        "checkpoints": CHECKPOINTS,
    }
    db.commit()

    update_client(db, client_a, ClientUpdate(lead_goal_overrides={"3": 42}))
    assert current_lead_goal(client_a, ANCHOR)[0] == 42

    # A fresh projection, as re-running the baseline would write.
    client_a.baseline_projection_json = {
        "baseline_as_of": ANCHOR.isoformat(),
        "checkpoints": [dict(row, monthly_leads=row["monthly_leads"] + 5) for row in CHECKPOINTS],
    }
    db.commit()

    goal, checkpoint = current_lead_goal(client_a, ANCHOR)
    assert goal == 42
    assert checkpoint.projected == 43


def test_junk_overrides_are_dropped_without_losing_the_good_ones(db, client_a):
    from app.services.clients import update_client
    from app.schemas import ClientUpdate

    update_client(
        db,
        client_a,
        ClientUpdate(lead_goal_overrides={"3": 42, "6": "nope", "bad": 10, "9": -1, "12": 60}),
    )

    assert client_a.lead_goal_overrides == {"3": 42, "12": 60}
