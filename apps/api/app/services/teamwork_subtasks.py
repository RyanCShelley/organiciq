"""Breaking a Teamwork task into subtasks, and finishing the job when a send stops halfway.

The parent task is made first and its id kept. Each subtask is made and recorded one at a time, so a Teamwork error leaves the ones that landed
recorded, and pressing send again makes only the rest. A subtask failing never un-sends the parent: the person has the task, and is told how
many subtasks are still to come.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.integrations import teamwork

#: A task with more parts than this is a plan, not a task; the rest stay in the parent's checklist.
MAX_SUBTASKS = 12


@dataclass(frozen=True)
class Sub:
    key: str  # stable across presses, so a retry knows which are done
    name: str
    description: str


def send(
    db: Session, record: Any, parent_id: str, subs: list[Sub], *, due: str | None, assignee: str | None,
) -> int:
    """Make the subtasks the record does not have yet. Returns how many are still missing (0 when all are there)."""
    made: dict[str, str] = dict(record.teamwork_subtasks or {})
    for sub in subs[:MAX_SUBTASKS]:
        if sub.key in made:
            continue
        try:
            created = teamwork.create_subtask(
                parent_task_id=parent_id, name=sub.name, description=sub.description, due=due, assignee_teamwork_id=assignee,
            )
        except teamwork.TeamworkError:
            break
        made[sub.key] = created["id"]
        record.teamwork_subtasks = dict(made)  # a new dict, so the change is seen
        db.commit()
    return sum(1 for sub in subs[:MAX_SUBTASKS] if sub.key not in made)


def assignee_id(email: str | None) -> str | None:
    """The Teamwork id for an address; None sends unassigned rather than not at all."""
    if not email:
        return None
    try:
        return teamwork.person_id_for(email, teamwork.list_people())
    except teamwork.TeamworkError:
        return None


def from_steps(steps: list[str], *, growth: bool) -> list[Sub]:
    """An engine task's checklist as subtasks.

    A growth action's steps come under "# " headings (its parts): each part is a subtask holding its steps. Any other task's steps are
    one subtask each.
    """
    subs: list[Sub] = []
    if growth:
        part: str | None = None
        items: list[str] = []

        def close() -> None:
            if part:
                subs.append(Sub(f"part-{len(subs) + 1}", part, "\n".join(f"[ ] {i}" for i in items) or part))

        for step in steps:
            if step.startswith("# "):
                close()
                part, items = step[2:].strip(), []
            elif part:
                items.append(step)
            else:  # steps before the first heading stand alone
                subs.append(Sub(f"step-{len(subs) + 1}", step[:120], step))
        close()
        return subs
    return [Sub(f"step-{i + 1}", _short(step), step) for i, step in enumerate(steps) if step.strip()]


def _short(step: str) -> str:
    first = step.strip().splitlines()[0]
    return first if len(first) <= 120 else first[:117].rstrip() + "…"
