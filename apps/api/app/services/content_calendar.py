"""The content calendar: pages to write and pages to refresh, planned by people.

An item is added from a content gap (a new page), a content refresh (an existing page) or by hand. Adding from a gap or a refresh copies
the model's brief or refresh plan into the item's notes if one was written, so the person doing the work has it. Items can be sent to the
client's Teamwork tasklist as a task; nothing is sent until a person presses send.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.integrations import teamwork
from app.models.client import Client
from app.models.schema_tools import ContentItem
from app.services import content_briefs

KINDS = ("new_page", "refresh")
SOURCES = ("gap", "refresh", "topic", "manual")
STATUSES = ("idea", "planned", "writing", "review", "published", "dropped")
LIMIT = 500


def out(item: ContentItem) -> dict[str, Any]:
    return {
        "id": str(item.id), "kind": item.kind, "title": item.title, "target": item.target, "source_area": item.source_area, "source_key": item.source_key,
        "status": item.status, "due": item.due.isoformat() if item.due else None, "assignee_email": item.assignee_email, "notes": item.notes,
        "teamwork_task_id": item.teamwork_task_id, "teamwork_task_url": item.teamwork_task_url,
        "published_at": item.published_at.isoformat() if item.published_at else None, "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _flat(value: Any) -> str:
    """A list entry as one line: plain text, or the plan's {section|what, why} pairs as "what: why"."""
    if isinstance(value, dict):
        head = str(value.get("section") or value.get("what") or "").strip()
        why = str(value.get("why") or "").strip()
        return f"{head}: {why}" if head and why else head or why
    return str(value).strip()


def _lines(label: str, values: Any) -> list[str]:
    values = [_flat(v) for v in (values or []) if _flat(v)]
    return ["", label, *[f"- {v}" for v in values]] if values else []


def notes_from_draft(db: Session, client: Client, source_area: str, source_key: str | None) -> str | None:
    """The brief (for a gap) or refresh plan (for a page) the model already wrote, as plain words. None when there is none."""
    if source_area not in ("gap", "refresh", "topic") or not source_key:
        return None
    draft = content_briefs.latest(db, client, {"gap": "brief", "topic": "tbrief", "refresh": "refresh"}[source_area], source_key)
    if not draft or draft.get("status") != "done":
        return None
    out_lines: list[str] = []
    if source_area in ("gap", "topic"):
        if draft.get("working_title"):
            out_lines.append(f"Working title: {draft['working_title']}")
        if draft.get("page_type"):
            out_lines.append(f"Page type: {draft['page_type']}")
        if draft.get("angle"):
            out_lines += ["", str(draft["angle"])]
        out_lines += _lines("Sections", draft.get("sections")) + _lines("Questions to answer", draft.get("questions")) + _lines("Cover", draft.get("entities"))
        if draft.get("target_words"):
            out_lines += ["", f"Aim for about {draft['target_words']} words"]
        out_lines += _lines("Avoid", draft.get("avoid"))
        out_lines += _lines("Link from", [f"{x.get('url')}  (anchor idea: {x.get('anchor_idea')})" for x in draft.get("link_from") or [] if isinstance(x, dict)])
    else:
        if draft.get("diagnosis"):
            out_lines += [str(draft["diagnosis"])]
        out_lines += _lines("Keep", draft.get("keep")) + _lines("Add", draft.get("add")) + _lines("Change", draft.get("change")) + _lines("Remove", draft.get("remove"))
        if draft.get("merge_with"):
            out_lines += ["", f"Consider merging with: {draft['merge_with']}"]
    text = "\n".join(out_lines).strip()
    return text or None


def index(db: Session, client: Client) -> dict[str, dict[str, str]]:
    """Which gaps and pages are already on the calendar, and where they stand: {gap: {search: status}, refresh: {url: status}}."""
    result: dict[str, dict[str, str]] = {"gap": {}, "refresh": {}, "topic": {}}
    for item in db.query(ContentItem).filter(ContentItem.client_id == client.id, ContentItem.source_area.in_(("gap", "refresh", "topic")), ContentItem.status != "dropped"):
        if item.source_key:
            result[item.source_area][item.source_key] = item.status
    return result


def add(
    db: Session, client: Client, *, email: str, kind: str, title: str, target: str, source_area: str, source_key: str | None,
    due: date | None, assignee_email: str | None, notes: str | None,
) -> tuple[ContentItem, bool]:
    """Add an item. A gap or page already on the calendar (and not dropped) is returned as it is, not added twice."""
    if source_key:
        held = db.query(ContentItem).filter(ContentItem.client_id == client.id, ContentItem.source_area == source_area, ContentItem.source_key == source_key, ContentItem.status != "dropped").first()
        if held is not None:
            return held, False
    item = ContentItem(
        client_id=client.id, kind=kind, title=title.strip(), target=target.strip(), source_area=source_area, source_key=source_key,
        status="planned" if due else "idea", due=due, assignee_email=assignee_email or None,
        notes=notes if notes is not None else notes_from_draft(db, client, source_area, source_key), created_by=email,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item, True


def description(item: ContentItem, client: Client) -> tuple[str, str]:
    is_new = item.kind == "new_page"
    name, text = teamwork.task_body(
        title=f"{'Write' if is_new else 'Refresh'}: {item.title}",
        why=item.notes,
        done_when=("The page is written, published and linked from the pages that should point to it." if is_new else "The changes are made and the page is republished with its updated date."),
        target_url=None if is_new else item.target,
        metric="organic search clicks and sessions" if not is_new else None,
        check_on=None,
        effort_min=None,
        record_url=f"{get_settings().web_v2_app_url.rstrip('/')}/{client.slug}/content-calendar",
    )
    if is_new:
        text = f"{'Subject to cover' if item.source_area == 'topic' else 'Search to win'}: {item.target}\n\n{text}"
    return name, text


def send(db: Session, client: Client, item: ContentItem) -> ContentItem:
    """Create the Teamwork task. Raises teamwork.TeamworkError when it cannot; a second press leaves the first task."""
    if item.teamwork_task_id:
        return item
    if not client.teamwork_tasklist_id:
        raise teamwork.TeamworkError("This client has no Teamwork tasklist yet. Choose one in Settings → Connections.")
    assignee = None
    if item.assignee_email:
        try:
            assignee = teamwork.person_id_for(item.assignee_email, teamwork.list_people())
        except teamwork.TeamworkError:
            assignee = None  # sent unassigned rather than not sent
    name, text = description(item, client)
    created = teamwork.create_task(tasklist_id=client.teamwork_tasklist_id, name=name, description=text, due=item.due.isoformat() if item.due else None, assignee_teamwork_id=assignee)
    item.teamwork_task_id, item.teamwork_task_url = str(created["id"]), created["url"]
    db.commit()
    db.refresh(item)
    return item


def set_status(item: ContentItem, status: str) -> None:
    item.status = status
    item.published_at = datetime.now(timezone.utc) if status == "published" else None
