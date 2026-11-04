"""What the copilot can look at.

Every tool is read-only and receives the client the request was already
authorised for: the model never names a client, so it cannot ask about another
one. Tools return plain JSON-able dicts, compacted so one result cannot flood
the model's context.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.copilot import playbook
from app.models.client import Client
from app.models.decision import MonthlyRecord
from app.services import engine_actions
from app.services.dashboard import build_dashboard
from app.services.data_health import load_client_data_health
from app.services.monthly_run import month_key

MAX_RESULT_CHARS = 9000
_MONTH = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class ToolContext:
    db: Session
    client: Client


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[[ToolContext, dict[str, Any]], dict[str, Any]]

    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def compact(value: Any, *, max_chars: int = MAX_RESULT_CHARS) -> Any:
    """Shrink a payload until it serialises under `max_chars`.

    Lists are cut and long strings trimmed, progressively, so the shape the
    model sees stays the same and only the tail goes. A cut list gets a
    `_truncated` marker so the model says so instead of treating it as whole.
    """

    def shrink(v: Any, list_cap: int, str_cap: int, depth: int) -> Any:
        if isinstance(v, dict):
            if depth <= 0:
                return {"_truncated": f"{len(v)} keys"}
            return {k: shrink(x, list_cap, str_cap, depth - 1) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            items = [shrink(x, list_cap, str_cap, depth - 1) for x in v[:list_cap]]
            if len(v) > list_cap:
                items.append({"_truncated": f"{len(v) - list_cap} more"})
            return items
        if isinstance(v, str) and len(v) > str_cap:
            return v[:str_cap] + "…"
        return v

    for list_cap, str_cap, depth in ((25, 400, 6), (10, 240, 5), (5, 120, 4), (3, 80, 3)):
        out = shrink(value, list_cap, str_cap, depth)
        if len(json.dumps(out, default=str)) <= max_chars:
            return out
    return {"_truncated": "result too large; ask for a narrower view"}


def _month_arg(args: dict[str, Any]) -> str | None:
    raw = args.get("month")
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str) or not _MONTH.match(raw):
        raise ValueError("month must look like 2026-10")
    return raw


def _record_for(ctx: ToolContext, month: str | None) -> MonthlyRecord | None:
    if month:
        return engine_actions.load_record(ctx.db, ctx.client, month)
    return (
        ctx.db.query(MonthlyRecord)
        .filter(MonthlyRecord.client_id == ctx.client.id)
        .order_by(MonthlyRecord.month.desc())
        .first()
    )


def _get_data_health(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {"sources": load_client_data_health(ctx.db, ctx.client.id)}


def _get_metrics(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    days = int(args.get("days") or 28)
    if not 7 <= days <= 120:
        raise ValueError("days must be between 7 and 120")
    to_date = date.today() - timedelta(days=1)
    from_date = to_date - timedelta(days=days - 1)
    return {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "dashboard": compact(build_dashboard(ctx.db, ctx.client, from_date, to_date)),
    }


def _get_month_plan(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    month = _month_arg(args)
    row = _record_for(ctx, month)
    if row is None:
        return {"found": False, "month": month or month_key(date.today())}
    return {
        "found": True,
        "month": row.month,
        "saved_at": row.run_saved_at.isoformat() if row.run_saved_at else None,
        "data_through": row.data_through.isoformat() if row.data_through else None,
        "constraint": row.constraint_name,
        "held_since": row.held_since,
        "confidence": row.confidence,
        "record": compact(row.record),
    }


def _get_action_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    month = _month_arg(args)
    row = _record_for(ctx, month)
    if row is None:
        return {"found": False, "month": month}
    slots = engine_actions.slots_in_record(row.record)
    work = engine_actions.list_workflow(ctx.db, ctx.client, row.month)
    states = [
        {
            **engine_actions.serialise(w, slot=slots.get(w.uid)),
            "title": slots[w.uid].title if w.uid in slots else None,
            "target_url": slots[w.uid].target_url if w.uid in slots else None,
        }
        for w in work
    ]
    return {"found": True, "month": row.month, "workflow": compact(states)}


def _search_playbook(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    hits = playbook.search(query)
    return {
        "matches": [
            {"source": s.source, "section": s.heading, "text": s.text[:3000]} for s in hits
        ]
    }


_MONTH_PROP = {
    "month": {
        "type": "string",
        "description": "Month as YYYY-MM. Omit for the most recent saved run.",
    }
}

TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "get_data_health",
            "Freshness and connection status of each data source for this client "
            "(Search Console, GA4, SE Ranking, site crawl): healthy, stale or not connected, "
            "with the date each is current through. Use first when numbers look wrong.",
            {"type": "object", "properties": {}},
            _get_data_health,
        ),
        Tool(
            "get_metrics",
            "This client's dashboard figures over the last N days ending yesterday: "
            "traffic, leads, search visibility, AI presence, top pages. Figures only; "
            "cite them as returned.",
            {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Window length, 7 to 120. Default 28."}
                },
            },
            _get_metrics,
        ),
        Tool(
            "get_month_plan",
            "The saved Decision Engine run for a month: the constraint, why, confidence, "
            "branch test results, the prescribed actions, empty slots, incidents and data gaps.",
            {"type": "object", "properties": _MONTH_PROP},
            _get_month_plan,
        ),
        Tool(
            "get_action_status",
            "Where each prescribed action stands for a month: planned, assigned, done or "
            "skipped, who has it, due date, whether it was sent to Teamwork or shipped.",
            {"type": "object", "properties": _MONTH_PROP},
            _get_action_status,
        ),
        Tool(
            "search_playbook",
            "Search the Organic IQ process and the SEO/GEO best-practice notes. Use for "
            "'what should we do about X' and 'what do the rules say' questions.",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            _search_playbook,
        ),
    )
}


def tool_specs() -> list[dict[str, Any]]:
    return [t.spec() for t in TOOLS.values()]


def run_tool(ctx: ToolContext, name: str, raw_args: str | dict[str, Any] | None) -> dict[str, Any]:
    """Run one tool call. Never raises: a bad call becomes an `error` the model
    can read and correct, which is how a small model recovers from a typo."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"unknown tool {name!r}", "available": sorted(TOOLS)}
    try:
        if isinstance(raw_args, str):
            args = json.loads(raw_args) if raw_args.strip() else {}
        else:
            args = raw_args or {}
        if not isinstance(args, dict):
            raise ValueError("arguments must be a JSON object")
        return tool.run(ctx, args)
    except (ValueError, TypeError) as exc:
        return {"error": str(exc)}
