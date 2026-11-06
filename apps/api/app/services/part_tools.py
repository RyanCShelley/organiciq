"""Which tool does each part of an action: the link from a decision to the screen that carries it out.

A growth action is made of parts (rewrite the title, add internal links, mark up the FAQ). Each part has an id from the Decision engine's catalog, and
each id belongs to one tool. The tool screens open on the page itself from the link. A part no tool covers is a plain step.
"""

from __future__ import annotations

import re
from typing import Any

#: tool key -> what a person sees, the screen's route, and the search parameter that opens its pane on the page.
TOOLS: dict[str, dict[str, str]] = {
    "ctr": {"label": "CTR optimizer", "path": "/ctr", "param": "page", "verb": "Rewrite the title"},
    "inlinks": {"label": "Inlink suggester", "path": "/inlinks", "param": "target", "verb": "Add the internal links"},
    "schema": {"label": "Machine readability", "path": "/schema", "param": "page", "verb": "Write the markup"},
    "optimizer": {"label": "Content optimizer", "path": "/content-optimizer", "param": "page", "verb": "Make the change"},
    "refresh": {"label": "Content refreshes", "path": "/content-refreshes", "param": "page", "verb": "Plan the refresh"},
    "gaps": {"label": "Content gaps", "path": "/content-gaps", "param": "term", "verb": "Plan the new page"},
}

#: part id -> tool. A part not listed here has no tool.
PART_TOOL = {
    "S-5": "ctr", "T-1": "ctr",
    "A-1": "optimizer", "P-1": "optimizer", "S-1": "optimizer", "S-2": "optimizer",
    "V-4": "inlinks", "S-4": "inlinks", "U-6": "inlinks",
    "V-7": "schema", "V-3": "schema",
    "S-3": "refresh", "T-S1": "refresh", "T-S2": "refresh", "L-S1": "refresh",
    "U-1": "refresh", "U-2": "refresh", "U-3": "refresh", "U-5": "refresh",
    "C-1": "gaps", "C-2": "gaps",
}
#: A part the optimizer does: which change it asks for (opening, terms, faq). The screen opens on that change.
PART_KIND = {"A-1": "opening", "P-1": "opening", "S-1": "terms", "S-2": "faq"}
#: What each optimizer part says on its button.
KIND_VERB = {"opening": "Rewrite the opening", "terms": "Work in the terms", "faq": "Write the FAQ"}

#: The names a growth action gives its parts (services/growth_action.PART_NAMES), to read the part ids back from the headings of a task made before ids were stored.
_BY_NAME = {
    "answer the question at the top": "A-1",
    "use the phrasing people search": "S-1",
    "add a short faq": "S-2",
    "mark up the faq": "V-7",
    "rewrite the opening": "P-1",
    "reread the title and description": "S-5",
    "link here from related pages": "S-4",
    "add internal links": "V-4",
}
_HEADING = re.compile(r"^#\s*(?:\d+\.\s*)?(.+)$")


def tool_for(part_id: str) -> dict[str, str] | None:
    key = PART_TOOL.get(part_id)
    if not key:
        return None
    tool = {"key": key, **TOOLS[key]}
    kind = PART_KIND.get(part_id)
    if kind:
        tool["kind"], tool["verb"] = kind, KIND_VERB[kind]
    return tool


def from_steps(steps: list[str]) -> list[dict[str, Any]]:
    """The parts of a growth action, read from its checklist ("# 1. Add internal links"). Used for a task that was confirmed before its parts were stored."""
    out: list[dict[str, Any]] = []
    for step in steps or []:
        m = _HEADING.match(step.strip()) if step.startswith("#") else None
        if m:
            name = m.group(1).strip()
            out.append({"id": _BY_NAME.get(name.lower(), ""), "name": name})
    return out


def describe(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each part with its tool, and where it stands. A part is open until it is marked done."""
    out = []
    for p in parts:
        tool = tool_for(str(p.get("id") or ""))
        out.append({
            "id": p.get("id") or "", "name": p.get("name") or "", "tool": tool["key"] if tool else None, "tool_label": tool["label"] if tool else None,
            "tool_path": tool["path"] if tool else None, "tool_param": tool["param"] if tool else None, "tool_verb": tool["verb"] if tool else None, "tool_kind": tool.get("kind") if tool else None,
            "status": p.get("status") or "open", "done_at": p.get("done_at"), "done_by": p.get("done_by"), "done_how": p.get("done_how"),
            "verified_at": p.get("verified_at"), "verified_how": p.get("verified_how"), "last_check": p.get("last_check"), "auto": not p.get("no_auto"),
        })
    return out
