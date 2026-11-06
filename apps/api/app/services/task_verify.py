"""Has the change gone live? The page is read and each open part is checked against what the page looked like when the action was confirmed.

The loop this closes is analysis, decision, execution, verified, annotated, measured. A part is marked done by a person, or by this check when the
page itself shows the change. Each check says exactly what it saw and where: "the title changed from X to Y, read from <address> on <date>".

Rules that keep it honest:
- Only the live page counts. A bot check, an error or an empty answer is "could not read", never "not live", and the crawl's older copy is never used to
  say a change is live.
- What the page looked like before comes from the site crawl at the time the action was confirmed. Without it, only checks that need no "before" run.
- A part a person took back is left alone by the daily run (it can still be checked by hand).
- Kinds of change that cannot be seen on a page are never marked: they stay for a person to mark.
"""

from __future__ import annotations

import difflib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.urls import normalize_url
from app.models.annotation import Annotation
from app.models.client import Client
from app.models.crawl import FactCrawlPageSchema
from app.models.engine_task import EngineTask
from app.models.schema_tools import ContentModelRun, InlinkState
from app.services import crawl_fallback, page_diagnostic, part_done
from app.services.page_diagnostic import PageUnreadable, parse_fetched, read_page, unreadable_reason
from app.services.schema_pages import content_text

logger = logging.getLogger("organiciq.task_verify")

CHECK_DAYS = 45
OPENING_CHANGED_BELOW = 0.85
_NOUN = {"S-5": "title or description", "A-1": "opening", "P-1": "opening", "S-2": "FAQ", "V-7": "FAQ markup", "S-1": "reworded sentences", "V-4": "internal links", "S-4": "internal links"}


def _opening(sections: list[Any]) -> str:
    out = []
    for s in sections or []:
        para = s.get("first_paragraph") if isinstance(s, dict) else getattr(s, "first_paragraph", "")
        if para:
            out.append(" ".join(str(para).split()))
    return " ".join(out)[:900]


def _questions(items: list[str] | None) -> list[str]:
    return [" ".join(q.split()).lower() for q in (items or [])]


def state_from_snapshot(db: Session, client: Client, url: str) -> dict[str, Any] | None:
    """What the crawl held for the page: the "before" of every check."""
    snap = crawl_fallback.snapshot_for(db, client, url)
    if snap is None:
        return None
    types = sorted({t for (t,) in db.query(FactCrawlPageSchema.schema_type).filter(FactCrawlPageSchema.client_id == client.id, FactCrawlPageSchema.normalized_url == snap.normalized_url) if t})
    return {
        "from": "crawl", "date": snap.snapshot_date.isoformat(), "title": snap.title or "", "description": snap.description or "", "opening": _opening(snap.sections or []),
        "faq_questions": _questions(snap.faq_questions), "schema_types": types, "word_count": snap.word_count, "updated_on": snap.content_updated_on.isoformat() if snap.content_updated_on else None,
    }


def state_from_page(parsed: Any, found: Any) -> dict[str, Any]:
    return {
        "from": "live", "date": datetime.now(timezone.utc).date().isoformat(), "title": parsed.title or "", "description": parsed.description or "", "opening": _opening(parsed.sections),
        "faq_questions": _questions(parsed.faq_questions), "schema_types": sorted({b.schema_type for b in parsed.schema_blocks if b.schema_type}), "word_count": parsed.word_count,
        "updated_on": parsed.content_updated_on.isoformat() if parsed.content_updated_on else None,
    }


def capture_before(db: Session, client: Client, task: EngineTask) -> None:
    """Keep the page as the crawl last saw it on every part, at the moment the action is confirmed. Does not commit."""
    before = state_from_snapshot(db, client, task.page_url)
    parts = part_done.parts_of(task)
    for p in parts:
        if before and "before" not in p:
            p["before"] = before
    task.parts = parts


# ── one check per kind of part ───────────────────────────────────────────────

Verdict = tuple[str, str]  # ("live" | "not_live" | "cannot", what was seen)


def _changed(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() < OPENING_CHANGED_BELOW


def _check_title(live: dict, before: dict | None, **_: Any) -> Verdict:
    if not before:
        return "cannot", "There is no earlier copy of the page to compare the title and description with."
    if live["title"] != before["title"] and live["title"]:
        return "live", f"the title changed from “{before['title']}” to “{live['title']}”"
    if live["description"] != before["description"] and live["description"]:
        return "live", f"the meta description changed from “{before['description'][:120]}” to “{live['description'][:120]}”"
    return "not_live", f"the title is still “{live['title']}” and the description is unchanged"


def _check_opening(live: dict, before: dict | None, **_: Any) -> Verdict:
    if not before or not before.get("opening"):
        return "cannot", "There is no earlier copy of the opening to compare with."
    if not live["opening"]:
        return "cannot", "No opening paragraph could be found on the page."
    if _changed(live["opening"], before["opening"]):
        return "live", f"the opening now reads “{live['opening'][:200]}” (it was “{before['opening'][:200]}”)"
    return "not_live", "the opening reads the same as before"


def _check_faq(live: dict, before: dict | None, **_: Any) -> Verdict:
    now, was = len(live["faq_questions"]), len((before or {}).get("faq_questions") or [])
    if before is None:
        return ("live", f"the page has {now} questions it answers") if now >= 2 else ("not_live", "the page has no FAQ questions")
    if now > was:
        new = [q for q in live["faq_questions"] if q not in before["faq_questions"]][:3]
        return "live", f"the page answers {now - was} more question{'s' if now - was != 1 else ''} than before (" + "; ".join(new) + ")"
    return "not_live", f"the page answers {now} questions, no more than before"


def _check_markup(live: dict, before: dict | None, **_: Any) -> Verdict:
    if "FAQPage" in live["schema_types"]:
        return "live", "the page now carries FAQPage markup" if before and "FAQPage" not in before["schema_types"] else "the page carries FAQPage markup"
    return "not_live", "the page carries no FAQPage markup"


def _check_terms(live: dict, before: dict | None, *, text: str, db: Session, client: Client, task: EngineTask, **_: Any) -> Verdict:
    row = db.query(ContentModelRun).filter(ContentModelRun.client_id == client.id, ContentModelRun.kind == "terms", ContentModelRun.key == normalize_url(task.page_url), ContentModelRun.status == "done").order_by(ContentModelRun.created_at.desc()).first()
    edits = ((row.payload or {}).get("edits") or []) if row else []
    if not edits:
        return "cannot", "No reworded sentences were written in the Content optimizer for this page, so there is nothing to look for."
    flat = " ".join(text.split()).lower()
    found = [e["after"] for e in edits if " ".join(e["after"].split()).lower() in flat]
    return ("live", f"{len(found)} of the {len(edits)} reworded sentences are on the page") if found else ("not_live", f"none of the {len(edits)} reworded sentences are on the page yet")


def _check_links(live: dict, before: dict | None, *, db: Session, client: Client, task: EngineTask, **_: Any) -> Verdict:
    target = normalize_url(task.page_url)
    since = task.confirmed_at
    rows = [r for r in db.query(InlinkState).filter(InlinkState.client_id == client.id, InlinkState.status == "live") if normalize_url(r.target_url) == target and (since is None or (r.checked_at and r.checked_at >= since))]
    if rows:
        return "live", f"{len(rows)} link{'s' if len(rows) != 1 else ''} to this page confirmed live in the Inlink suggester (e.g. from {rows[0].source_url})"
    return "not_live", "no link to this page has been confirmed live in the Inlink suggester since the action was confirmed"


_CHECKS = {"S-5": _check_title, "A-1": _check_opening, "P-1": _check_opening, "S-2": _check_faq, "V-7": _check_markup, "S-1": _check_terms, "V-4": _check_links, "S-4": _check_links}


def verdict_for(part: dict[str, Any], live: dict, *, text: str, db: Session, client: Client, task: EngineTask) -> Verdict:
    fn = _CHECKS.get(str(part.get("id") or ""))
    if fn is None:
        return "cannot", "This kind of change cannot be seen on the page, so it stays for a person to mark done."
    return fn(live, part.get("before"), text=text, db=db, client=client, task=task)


# ── the check ────────────────────────────────────────────────────────────────


async def _live_fetch(url: str):
    return await page_diagnostic._fetch(url)  # looked up at call time, never the crawl's copy


def _stamp(result: str, note: str) -> dict[str, str]:
    return {"at": datetime.now(timezone.utc).isoformat(), "result": result, "note": note}


def check_task(db: Session, client: Client, task: EngineTask, *, force: bool = False, fetch=None) -> dict[str, Any]:
    """Read the live page and check every part still waiting. A part the page shows is marked done, with how it was known."""
    parts = part_done.parts_of(task)
    wanted = [i for i, p in enumerate(parts) if (p.get("status") != "done" or not p.get("verified_at")) and (force or not p.get("no_auto"))]
    summary = {"checked": len(wanted), "live": 0, "unreadable": None}
    if not wanted:
        return summary
    try:
        found = read_page(task.page_url, client.domain, fetch or _live_fetch)
        parsed = parse_fetched(found)
        blocked = unreadable_reason(found, parsed)
        if not blocked and found.status >= 400:
            blocked = f"The page answered with an error ({found.status})."
    except PageUnreadable as exc:
        found, parsed, blocked = None, None, str(exc)
    except Exception as exc:  # noqa: BLE001 - a failed read is a note on each part, never a crash of the run
        found, parsed, blocked = None, None, f"The page could not be fetched ({type(exc).__name__})."
    if blocked:
        for i in wanted:
            parts[i]["last_check"] = _stamp("unreadable", f"Could not read the page, so nothing was judged: {blocked}")
        task.parts = parts
        db.commit()
        summary["unreadable"] = blocked
        return summary
    live, text = state_from_page(parsed, found), content_text(found.body)
    seen: dict[int, str] = {}
    for i in wanted:
        verdict, how = verdict_for(parts[i], live, text=text, db=db, client=client, task=task)
        if verdict == "live":
            seen[i] = f"Read live from {found.final_url} on {datetime.now(timezone.utc):%b %d, %Y at %H:%M} UTC: {how}."
            parts[i]["last_check"] = _stamp("live", how)
        else:
            parts[i]["last_check"] = _stamp(verdict, how if verdict == "cannot" else f"Read live on {datetime.now(timezone.utc):%b %d}: {how}. Not seen yet.")
    task.parts = parts
    db.commit()
    for i, how in seen.items():
        if parts[i].get("status") == "done":
            fresh = part_done.parts_of(task)
            fresh[i].update(verified_at=datetime.now(timezone.utc).isoformat(), verified_how=how)
            task.parts = fresh
            db.query(Annotation).filter(Annotation.client_id == client.id, Annotation.engine_uid == part_done.uid(task, i)).update({"verified_how": how})
            db.commit()
        else:
            part_done.set_part(db, client, task, i, True, "the live check", verified=how)
        summary["live"] += 1
    return summary


def maybe_check_open(db: Session) -> bool:
    """Once a day, read the live page of every recent action with a part still waiting. One page or one client failing does not stop the rest."""
    from app.core.settings import get_settings
    from app.models.scheduler import SchedulerCheckpoint
    from sqlalchemy.exc import IntegrityError

    now = datetime.now(timezone.utc)
    if now.hour < get_settings().task_verify_hour_utc:
        return False
    checkpoint = db.query(SchedulerCheckpoint).filter(SchedulerCheckpoint.name == "task_verify").with_for_update().one_or_none()
    if checkpoint is None:
        checkpoint = SchedulerCheckpoint(name="task_verify", last_run_date=None)
        db.add(checkpoint)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return False
    if checkpoint.last_run_date == now.date():
        db.rollback()
        return False
    checkpoint.last_run_date, checkpoint.updated_at = now.date(), now
    db.commit()
    since = now - timedelta(days=CHECK_DAYS)
    months = {now.strftime("%Y-%m"), (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")}
    for task in db.query(EngineTask).filter(EngineTask.month.in_(months), EngineTask.status != "dropped", EngineTask.confirmed_at >= since).limit(300).all():
        try:
            client = db.get(Client, task.client_id)
            if client is not None:
                from app.services import teamwork_sync

                teamwork_sync.sync_task(db, client, task)
                check_task(db, client, task)
        except Exception:  # noqa: BLE001 - one task must not stop the rest
            db.rollback()
            logger.exception("The live check failed for task %s", task.id)
    return True
