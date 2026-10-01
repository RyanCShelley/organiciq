"""The lead goal for where a client is in its contract, not where it ends up.

The dashboard showed `monthly_lead_goal`, which is the twelve-month target. In
month one that is the wrong number to judge a thirty-day review against: a
client on track to reach fifty leads a year from now reads as badly behind
against fifty today, and the honest answer — "that is the target for next
September" — is no use in the room.

The projection already holds the staircase. This reads it.

Which step applies
------------------
The goal is the next checkpoint ahead of you, held until you pass it. So for a
client three months in, the goal is the six-month figure it is now working
toward, and the three-month one it has already passed is history. Past the end
of the plan the final checkpoint holds, because there is nothing further to aim
at and a goal that vanishes is worse than one that stops moving.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

DAYS_PER_MONTH = 365 / 12


@dataclass(frozen=True)
class GoalCheckpoint:
    """One step of the staircase."""

    month: int
    goal: int
    #: What the projection said, before any correction.
    projected: int | None
    overridden: bool
    #: When this checkpoint falls, if the baseline date is known.
    due: date | None
    #: The step the client is working toward now.
    current: bool


def _anchor(client: Any) -> date | None:
    projection = client.baseline_projection_json or {}
    raw = projection.get("baseline_as_of") if isinstance(projection, dict) else None
    for value in (raw, client.baseline_period_end, client.baseline_as_of):
        if isinstance(value, date):
            return value
        if isinstance(value, str) and value:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                continue
    return None


def _checkpoints(client: Any) -> list[dict[str, Any]]:
    projection = client.baseline_projection_json or {}
    if not isinstance(projection, dict):
        return []
    rows = projection.get("checkpoints")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("month") is not None]


def _override_for(client: Any, month: int) -> int | None:
    overrides = client.lead_goal_overrides or {}
    if not isinstance(overrides, dict):
        return None
    value = overrides.get(str(month), overrides.get(month))
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def months_elapsed(client: Any, on: date | None = None) -> float | None:
    """How far into the plan the client is, in months."""
    anchor = _anchor(client)
    if anchor is None:
        return None
    return max(((on or date.today()) - anchor).days / DAYS_PER_MONTH, 0.0)


def goal_schedule(client: Any, on: date | None = None) -> list[GoalCheckpoint]:
    """Every checkpoint, with the one in force marked."""
    rows = _checkpoints(client)
    if not rows:
        return []

    anchor = _anchor(client)
    elapsed = months_elapsed(client, on)
    ordered = sorted(rows, key=lambda row: int(row["month"]))

    # Month zero is the baseline itself — where the client started, not
    # something to aim at — so it is never the current step.
    future = [row for row in ordered if int(row["month"]) > 0]
    current_month: int | None = None
    if future and elapsed is not None:
        ahead = [row for row in future if int(row["month"]) >= elapsed]
        current_month = int((ahead or future[-1:])[0]["month"])

    schedule: list[GoalCheckpoint] = []
    for row in ordered:
        month = int(row["month"])
        projected_raw = row.get("monthly_leads")
        projected = (
            int(round(float(projected_raw))) if isinstance(projected_raw, (int, float)) else None
        )
        override = _override_for(client, month)
        goal = override if override is not None else (projected or 0)
        due = None
        if anchor is not None:
            due = date.fromordinal(anchor.toordinal() + int(round(month * DAYS_PER_MONTH)))
        schedule.append(
            GoalCheckpoint(
                month=month,
                goal=goal,
                projected=projected,
                overridden=override is not None,
                due=due,
                current=month == current_month,
            )
        )
    return schedule


def current_lead_goal(client: Any, on: date | None = None) -> tuple[int | None, GoalCheckpoint | None]:
    """The monthly goal in force, and the checkpoint it comes from.

    Falls back to the client's flat `monthly_lead_goal` when there is no
    projection to read — a client without one still needs a number.
    """
    for checkpoint in goal_schedule(client, on):
        if checkpoint.current and checkpoint.goal > 0:
            return checkpoint.goal, checkpoint
    goal = client.monthly_lead_goal
    return (goal if goal and goal > 0 else None), None


def schedule_payload(client: Any, on: date | None = None) -> list[dict[str, Any]]:
    return [
        {
            "month": row.month,
            "goal": row.goal,
            "projected": row.projected,
            "overridden": row.overridden,
            "due": row.due.isoformat() if row.due else None,
            "current": row.current,
        }
        for row in goal_schedule(client, on)
    ]
