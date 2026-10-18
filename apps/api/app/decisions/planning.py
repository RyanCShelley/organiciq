"""Reviewed growth briefs, independent of the diagnostic branch ladder.

Rule IDs remain evidence references. A plan is a person's ordered decision,
and an approved snapshot survives a subsequent assessment run.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

from app.core.urls import normalize_url

FAMILIES = {
    "priority_page": "Improve or recover a priority page",
    "ai_answers": "Improve AI answers and citations",
    "internal_links": "Strengthen internal links",
    "conversion_path": "Improve conversion path",
    "structured_data": "Add or repair relevant structured data",
    "investigation": "Investigate a material change",
}


def page_identity(url: str) -> str:
    return normalize_url(url).split("://", 1)[-1]
RULE_FAMILY = {
    "V-1": "priority_page", "V-8": "priority_page", "T-1": "priority_page",
    "T-3": "priority_page", "V-2": "ai_answers", "V-5": "ai_answers",
    "T-2": "ai_answers", "V-4": "internal_links", "L-1": "conversion_path",
    "L-2": "conversion_path", "L-3": "conversion_path",
    "V-3": "structured_data", "V-7": "structured_data",
    "G-1": "ai_answers",
}


def proposals(data: dict) -> list[dict]:
    """Group findings by executable job and page, preserving every observation."""
    grouped: dict[tuple, dict] = {}
    for row in data.get("findings", data.get("candidates") or data.get("actions") or []):
        if row.get("id") == "V-6":
            continue  # ownership is setup, not a purchased growth job
        family = row.get("family") or RULE_FAMILY.get(row.get("id"), "investigation")
        key = (family, page_identity(row.get("target_url") or ""), row.get("term") if not row.get("target_url") else None)
        if key not in grouped:
            item = deepcopy(row)
            item.update(
                family=family, title=FAMILIES[family], slot=None,
                action_uid="brief-" + sha256(repr((data.get("month"), key)).encode()).hexdigest()[:24],
                finding_ids=[], evidence=[], steps=[],
            )
            grouped[key] = item
        item = grouped[key]
        item["finding_ids"] = list(dict.fromkeys([*item["finding_ids"], row.get("id")]))
        item["evidence"] = list(dict.fromkeys([*item["evidence"], *row.get("evidence", []), row.get("why", "")]))
        item["steps"] = list(dict.fromkeys([*item["steps"], *(row.get("steps") or [row.get("done_when", "")])]))
    return list(grouped.values())


def initial_review(data: dict) -> dict:
    # Preserve identities of legacy work so adoption never detaches assignments.
    items = []
    if not data.get("review_required"):
        for row in data.get("actions", []):
            if row.get("id") == "V-6":
                continue
            item = deepcopy(row)
            item.update(family=RULE_FAMILY.get(row.get("id"), "investigation"),
                        steps=row.get("steps") or [row.get("done_when") or "Review and specify the intervention."],
                        evidence=row.get("evidence") or [],
                        metric_key=row.get("metric_key") or ({"V-2": "ai_presence", "T-1": "page_clicks", "T-2": "page_clicks", "T-3": "engagement_rate", "L-1": "page_lead_rate", "L-2": "page_lead_rate", "L-3": "page_lead_rate"}.get(row.get("id"), "term_position" if row.get("id", "").startswith("V-") else "decision")),
                        finding_ids=[row.get("id")], check_after_days=28)
            items.append(item)
    return {"revision": 0, "strategy": "", "focus": "", "reason": "",
            "items": items, "approved_at": None, "approved_by": None, "versions": []}


def action_count(items: list[dict]) -> int:
    """Each selected intervention counts, even in a legacy page bundle."""
    return sum(max(1, len([s for s in item.get("steps", []) if s.strip()])) for item in items)


def validate_plan(review: dict, capacity: int) -> None:
    if not review.get("focus"):
        raise ValueError("Choose a focus before approving.")
    if action_count(review["items"]) > capacity:
        raise ValueError(f"This plan allows {capacity} growth actions. Remove an action before approving.")
    interventions: set[tuple[str, str]] = set()
    uids: set[str] = set()
    for item in review["items"]:
        if item["action_uid"] in uids:
            raise ValueError("An action appears twice in the plan.")
        uids.add(item["action_uid"])
        url = page_identity(item.get("target_url", ""))
        if not url:
            raise ValueError("Each growth brief needs a target page. New pages belong in the content pool.")
        for step in item.get("steps", []):
            key = (url, " ".join(step.lower().split()))
            if key in interventions:
                raise ValueError("The same action on the same page appears twice.")
            interventions.add(key)
        for field in ("title", "why", "done_when", "metric"):
            if not item.get(field, "").strip():
                raise ValueError(f"Every brief needs {field.replace('_', ' ')}.")
        if not item.get("steps"):
            raise ValueError("Every brief needs an executable checklist.")


def effective_record(data: dict, *, approved_only: bool = False) -> dict:
    """Overlay reviewed work for display/workflow; never overwrite assessment."""
    review = data.get("plan_review")
    if not review or (approved_only and not review.get("approved_at")):
        return deepcopy(data)
    out = deepcopy(data)
    out["action_slots"] = data.get("growth_capacity", data["action_slots"])
    out["engine_constraint"] = data.get("engine_constraint", data.get("constraint"))
    if review.get("focus"):
        out.update(constraint=review["focus"], reason_text=review.get("reason") or "Selected by the account lead after reviewing the findings.", override="manual")
    out["actions"] = [{**item, "slot": index + 1, "spillover": False}
                      for index, item in enumerate(review["items"])]
    out["candidates"] = out["actions"]
    out["empty_slots"] = []
    return out
