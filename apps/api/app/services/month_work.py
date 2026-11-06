"""A month's approved work, counted by the tool that does it: what is open, what is done, and what the page has been seen to show.

One place for the numbers, so the plan and the monthly review say the same thing.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.engine_task import EngineTask
from app.services import part_tools


def _parts(task: EngineTask) -> list[dict[str, Any]]:
    """The task's parts without changing it: stored ones, else read back from its checklist, else the task itself as one part."""
    if task.parts:
        return list(task.parts)
    return part_tools.from_steps(task.steps or []) or [{"id": task.rule_id if task.kind != "growth_action" else "", "name": task.title}]


def build(db: Session, client: Client, month: str) -> dict[str, Any]:
    tasks = db.query(EngineTask).filter(EngineTask.client_id == client.id, EngineTask.month == month, EngineTask.status != "dropped").order_by(EngineTask.confirmed_at).all()
    tools: dict[str, dict[str, Any]] = {}
    total = done = seen = 0
    for task in tasks:
        for index, part in enumerate(_parts(task)):
            tool = part_tools.tool_for(str(part.get("id") or ""))
            key = tool["key"] if tool else "none"
            row = tools.setdefault(key, {"tool": key, "label": tool["label"] if tool else "By hand", "path": tool["path"] if tool else None, "param": tool["param"] if tool else None, "open": 0, "done": 0, "seen_live": 0, "items": []})
            is_done = part.get("status") == "done"
            row["done" if is_done else "open"] += 1
            row["seen_live"] += 1 if part.get("verified_at") else 0
            total, done, seen = total + 1, done + (1 if is_done else 0), seen + (1 if part.get("verified_at") else 0)
            row["items"].append({"task_id": str(task.id), "part": index, "name": part.get("name") or task.title, "page": task.page_url, "search": task.search, "kind": tool.get("kind") if tool else None, "done": is_done, "seen_live": bool(part.get("verified_at"))})
    order = [k for k in ("ctr", "optimizer", "refresh", "gaps", "inlinks", "schema", "none") if k in tools]
    return {"month": month, "actions": len(tasks), "parts": total, "done": done, "open": total - done, "seen_live": seen, "by_tool": [tools[k] for k in order]}
