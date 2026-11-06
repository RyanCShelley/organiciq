"""A subtask finished in Teamwork marks its part done here.

Sending an action to Teamwork makes one subtask per part (`part-1`, `part-2`, ...). The people doing the work tick those off in Teamwork, so
this asks Teamwork, when the plan is checked and once a day, which of an action's subtasks are completed and marks those parts done, with who
completed them and when.

A tick in Teamwork says someone finished the work, not that the page shows it. So after marking, the live page is checked for the same parts:
when it shows the change the part says so, and when it does not the part reads "Done in Teamwork, not seen live yet". Nothing is ever written to
Teamwork, and un-completing a subtask there does not undo the part here (a part is undone on the plan).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.integrations import teamwork
from app.models.client import Client
from app.models.engine_task import EngineTask
from app.services import part_done

logger = logging.getLogger("organiciq.teamwork_sync")


def _subtask_ids(task: EngineTask, index: int, parts: list[dict[str, Any]]) -> list[str]:
    """The Teamwork subtasks that, when completed, finish this part. A growth action's parts are its subtasks; any other action is one part
    that all of its steps' subtasks make up."""
    made = dict(task.teamwork_subtasks or {})
    if task.kind == "growth_action":
        found = made.get(f"part-{index + 1}")
        return [found] if found else []
    return list(made.values()) if len(parts) == 1 else []


def sync_task(db: Session, client: Client, task: EngineTask, *, force: bool = False) -> dict[str, Any]:
    """Mark parts done for subtasks completed in Teamwork. Returns {"checked": n, "marked": n, "error": str | None}."""
    out: dict[str, Any] = {"checked": 0, "marked": 0, "error": None}
    if not task.teamwork_subtasks or not teamwork.configured():
        return out
    parts = part_done.parts_of(task)
    cache: dict[str, teamwork.TaskStatus] = {}
    for i, part in enumerate(parts):
        if part.get("status") == "done" or (part.get("no_auto") and not force):
            continue
        ids = _subtask_ids(task, i, parts)
        if not ids:
            continue
        out["checked"] += 1
        try:
            statuses = [cache[s] if s in cache else cache.setdefault(s, teamwork.task_status(s)) for s in ids]
        except teamwork.TeamworkError as exc:
            out["error"] = str(exc)
            break
        if not all(s.done for s in statuses):
            continue
        last = max(statuses, key=lambda s: s.completed_at or "")
        who = last.completed_by or "Teamwork"
        when = (last.completed_at or datetime.now(timezone.utc).isoformat())[:10]
        part_done.set_part(db, client, task, i, True, f"{who} in Teamwork", how=f"The Teamwork subtask was completed by {who} on {when}.")
        out["marked"] += 1
    return out
