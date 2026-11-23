"""Per-page edit and action history: crawl content diffs, Decision Engine tasks, and Annotations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.urls import normalize_url, url_variants
from app.decisions.action_context import REJECTION_REASONS
from app.models.annotation import Annotation
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.engine_task import EngineTask


def _summarize_diff(previous: list[Any] | None, current: list[Any] | None) -> dict[str, Any] | None:
    if not previous and not current:
        return None
    prev_texts = [
        " ".join(str(p.get("text") if isinstance(p, dict) else p).split())
        for p in (previous or [])
        if (p.get("text") if isinstance(p, dict) else p)
    ]
    curr_texts = [
        " ".join(str(p.get("text") if isinstance(p, dict) else p).split())
        for p in (current or [])
        if (p.get("text") if isinstance(p, dict) else p)
    ]
    prev_set = set(prev_texts)
    curr_set = set(curr_texts)
    added = [t[:160] for t in curr_texts if t not in prev_set][:3]
    removed = [t[:160] for t in prev_texts if t not in curr_set][:3]
    return {
        "previous_count": len(prev_texts),
        "current_count": len(curr_texts),
        "added_count": sum(1 for t in curr_texts if t not in prev_set),
        "removed_count": sum(1 for t in prev_texts if t not in curr_set),
        "added_samples": added,
        "removed_samples": removed,
    }


def for_page(db: Session, client: Client, page_url: str) -> dict[str, Any]:
    """Aggregate crawl change history, EngineTask actions (including rejections), and Annotations for `page_url`."""
    norm = normalize_url(page_url) or page_url
    urls = url_variants(page_url) or [page_url, norm]
    lower_urls = list({u.lower() for u in urls})

    snaps = (
        db.query(FactCrawlPageSnapshot)
        .filter(
            FactCrawlPageSnapshot.client_id == client.id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
            FactCrawlPageSnapshot.normalized_url.in_(urls),
        )
        .order_by(FactCrawlPageSnapshot.snapshot_date.desc())
        .all()
    )
    crawl_changes = []
    for s in snaps:
        crawl_changes.append(
            {
                "snapshot_date": s.snapshot_date.isoformat(),
                "content_updated_on": s.content_updated_on.isoformat() if s.content_updated_on else None,
                "content_changed_on": s.content_changed_on.isoformat() if s.content_changed_on else None,
                "previous_replaced_on": s.previous_replaced_on.isoformat() if s.previous_replaced_on else None,
                "title": s.title,
                "meta_description": s.description,
                "word_count": s.word_count,
                "paragraphs_count": len(s.paragraphs or []),
                "previous_paragraphs_count": len(s.previous_paragraphs or []),
                "diff_summary": _summarize_diff(s.previous_paragraphs, s.paragraphs) if s.previous_paragraphs is not None else None,
            }
        )

    task_rows = (
        db.query(EngineTask)
        .filter(
            EngineTask.client_id == client.id,
            or_(EngineTask.page_url.in_(urls), func.lower(EngineTask.page_url).in_(lower_urls)),
        )
        .order_by(EngineTask.confirmed_at.desc())
        .all()
    )
    tasks = []
    for t in task_rows:
        tasks.append(
            {
                "id": str(t.id),
                "month": t.month,
                "title": t.title,
                "status": t.status,
                "kind": t.kind,
                "rule_id": t.rule_id,
                "search": t.search,
                "parts": [
                    {"id": p.get("id") or "", "name": p.get("name") or "", "status": p.get("status") or "open"}
                    for p in (t.parts or [])
                ],
                "confirmed_by": t.confirmed_by,
                "confirmed_at": t.confirmed_at.isoformat() if t.confirmed_at else None,
                "sent_at": t.confirmed_at.isoformat() if t.teamwork_task_id and t.confirmed_at else None,
                "shipped_at": t.shipped_at.isoformat() if t.shipped_at else None,
                "rejected_at": t.rejected_at.isoformat() if t.rejected_at else None,
                "rejected_by": t.rejected_by,
                "rejection_reason": t.rejection_reason,
                "rejection_reason_label": REJECTION_REASONS.get(t.rejection_reason) if t.rejection_reason else None,
                "rejection_note": t.rejection_note,
                "created_at": t.confirmed_at.isoformat() if t.confirmed_at else None,
            }
        )

    ann_rows = (
        db.query(Annotation)
        .filter(
            Annotation.client_id == client.id,
            or_(Annotation.page_url.in_(urls), func.lower(Annotation.page_url).in_(lower_urls)),
        )
        .order_by(Annotation.date.desc(), Annotation.created_at.desc())
        .all()
    )
    annotations = []
    for a in ann_rows:
        annotations.append(
            {
                "id": str(a.id),
                "date": a.date.isoformat(),
                "annotation_type": a.annotation_type.value,
                "description": a.description,
                "verified_how": a.verified_how,
                "result": a.result.value if a.result else None,
                "notes": a.notes,
            }
        )

    return {
        "page": norm,
        "crawl_changes": crawl_changes,
        "tasks": tasks,
        "annotations": annotations,
    }
