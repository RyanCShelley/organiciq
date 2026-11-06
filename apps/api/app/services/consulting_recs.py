"""Consulting recommendations: the briefs a consultant writes, reviews and publishes to a client's portal, and what is known about what the client did.

Two tracks, kept apart on purpose:
- the review track is the consultant's (draft, under review, approved, published, archived). Only a published brief is ever shown to the client.
- the implementation track is the client's side, and is often unknown: the client may not answer. Its status says who reported it. Verified and measured are
  filled only when there is evidence, and "completed" is never read as verified.
Nothing here creates work for SMA: publishing only makes a brief visible.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.consulting import IMPL_STATUSES, REVIEW_STATES, ConsultingRecommendation, ConsultingRecommendationEvent

CATEGORIES = ("visibility", "traffic", "leads")
FOCI = ("seo", "geo", "both")
SOURCES = ("manual", "decision_engine", "site_health", "geo", "ctr", "inlinks", "schema", "content_gap", "content_refresh", "optimizer")
PRIORITIES = ("high", "medium", "low")
CONFIDENCE = ("high", "medium", "low")
CAUSES = ("hypothesis", "confirmed")
VERIFICATION = ("unverified", "verified", "not_seen", "unreadable")
IMPL_SOURCES = ("consultant", "client", "live_check")

#: Which states a brief may move to from where it is. One step back is always allowed; archived can be restored to draft.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("under_review", "approved", "archived"),
    "under_review": ("draft", "approved", "archived"),
    "approved": ("under_review", "published", "archived"),
    "published": ("approved", "archived"),
    "archived": ("draft",),
}

EDITABLE = (
    "title", "category", "focus", "source_kind", "source_ref", "finding", "explanation", "cause_kind", "cause_text", "action", "instructions", "target_urls",
    "priority", "expected_impact", "confidence", "confidence_reasons", "effort_min", "owner", "baseline", "success_metrics", "measure_on", "evidence", "internal_notes",
)


class RecError(ValueError):
    """A change that cannot be made, in words for the consultant."""


class RecConflict(RecError):
    """The brief changed in another window since it was opened."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log(db: Session, rec: ConsultingRecommendation, kind: str, who: str, *, frm: str | None = None, to: str | None = None, detail: dict | None = None) -> None:
    db.add(ConsultingRecommendationEvent(recommendation_id=rec.id, client_id=rec.client_id, kind=kind, from_value=frm, to_value=to, by=who, detail=detail or {}))


def _check(field: str, value: Any, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise RecError(f"{field} must be one of: {', '.join(allowed)}.")


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in data.items() if k in EDITABLE}
    for f, allowed in (("category", CATEGORIES), ("focus", FOCI), ("source_kind", SOURCES), ("priority", PRIORITIES), ("confidence", CONFIDENCE), ("cause_kind", CAUSES)):
        if f in out and out[f] is not None:
            _check(f, out[f], allowed)
    for f in ("title", "finding", "explanation", "cause_text", "action", "expected_impact", "owner", "internal_notes"):
        if f in out and isinstance(out[f], str):
            out[f] = out[f].strip() or None
    if "instructions" in out:
        out["instructions"] = [{"text": " ".join(str(i.get("text", i) if isinstance(i, dict) else i).split())} for i in (out["instructions"] or []) if (i.get("text") if isinstance(i, dict) else i)]
    if "target_urls" in out:
        out["target_urls"] = [{"url": str(u.get("url", u) if isinstance(u, dict) else u).strip(), "check": (u.get("check") if isinstance(u, dict) else None) or {"state": "unchecked"}} for u in (out["target_urls"] or []) if (u.get("url") if isinstance(u, dict) else u)]
    return out


def create(db: Session, client: Client, data: dict[str, Any], who: str) -> ConsultingRecommendation:
    clean = _clean(data)
    if not clean.get("title") or not clean.get("category"):
        raise RecError("A brief needs a title and a category (visibility, traffic or leads).")
    rec = ConsultingRecommendation(client_id=client.id, created_by=who, **clean)
    db.add(rec)
    db.flush()
    _log(db, rec, "created", who, to=rec.source_kind)
    db.commit()
    db.refresh(rec)
    return rec


def get(db: Session, client: Client, rec_id: UUID) -> ConsultingRecommendation | None:
    return db.query(ConsultingRecommendation).filter(ConsultingRecommendation.id == rec_id, ConsultingRecommendation.client_id == client.id).one_or_none()


def update(db: Session, rec: ConsultingRecommendation, data: dict[str, Any], revision: int, who: str) -> ConsultingRecommendation:
    """Edit a brief. The revision is the one the editor opened: if the brief moved on since, nothing is overwritten."""
    if rec.revision != revision:
        raise RecConflict("This brief changed in another window. Reload it before saving.")
    if rec.review_state == "archived":
        raise RecError("An archived brief cannot be edited. Restore it to draft first.")
    clean = _clean(data)
    changed = sorted(k for k, v in clean.items() if getattr(rec, k) != v)
    for k, v in clean.items():
        setattr(rec, k, v)
    if not changed:
        return rec
    rec.revision += 1
    if rec.review_state == "approved":
        # An approval covers the text that was approved: a changed brief is reviewed again.
        rec.review_state, rec.approved_at, rec.approved_by = "under_review", None, None
        _log(db, rec, "state", who, frm="approved", to="under_review", detail={"why": "edited after approval"})
    _log(db, rec, "edited", who, detail={"fields": changed, "published": rec.review_state == "published"})
    db.commit()
    db.refresh(rec)
    return rec


def publish_gaps(rec: ConsultingRecommendation) -> list[str]:
    """What a brief still lacks before a client can read it."""
    gaps = []
    if not rec.finding:
        gaps.append("what the evidence shows (finding)")
    if not rec.action:
        gaps.append("the recommended action")
    if not rec.instructions:
        gaps.append("at least one instruction step")
    if not rec.explanation:
        gaps.append("why it matters")
    return gaps


def transition(db: Session, rec: ConsultingRecommendation, to: str, who: str) -> ConsultingRecommendation:
    _check("state", to, REVIEW_STATES)
    if to not in TRANSITIONS[rec.review_state]:
        raise RecError(f"A {rec.review_state.replace('_', ' ')} brief cannot move to {to.replace('_', ' ')}.")
    if to == "published":
        gaps = publish_gaps(rec)
        if gaps:
            raise RecError("Before this can be published it needs: " + "; ".join(gaps) + ".")
    frm = rec.review_state
    rec.review_state = to
    now = _now()
    if to == "approved":
        rec.approved_at, rec.approved_by = now, who
    elif to == "published":
        rec.published_at, rec.published_by = now, who
        rec.archived_at = None
    elif to == "archived":
        rec.archived_at = now
    elif to in ("draft", "under_review"):
        rec.approved_at = rec.approved_by = None
        rec.archived_at = None
    rec.revision += 1
    _log(db, rec, "state", who, frm=frm, to=to)
    db.commit()
    db.refresh(rec)
    return rec


def record_progress(
    db: Session, rec: ConsultingRecommendation, *, status: str | None, source: str, who: str, implemented_on: date | None = None,
    estimated: bool = False, notes: str | None = None, links: list[str] | None = None,
) -> ConsultingRecommendation:
    """What the client's side did. Often the consultant recording what they were told, so the source says who reported it."""
    _check("source", source, IMPL_SOURCES)
    frm = rec.impl_status
    if status is not None:
        _check("status", status, IMPL_STATUSES)
        rec.impl_status = status
    rec.impl_status_source, rec.impl_updated_at = source, _now()
    if implemented_on is not None:
        rec.implemented_on, rec.implemented_on_estimated = implemented_on, estimated
    if notes is not None:
        rec.client_notes = notes.strip() or None
    if links is not None:
        rec.evidence_links = [l.strip() for l in links if l and l.strip()]
    _log(db, rec, "progress", who, frm=frm, to=rec.impl_status, detail={"source": source, "implemented_on": implemented_on.isoformat() if implemented_on else None, "estimated": estimated, "notes": notes})
    db.commit()
    db.refresh(rec)
    return rec


def record_verification(db: Session, rec: ConsultingRecommendation, state: str, how: str | None, who: str) -> ConsultingRecommendation:
    """Verified only on evidence: what was seen, where. A client marking it complete does not verify it."""
    _check("verification", state, VERIFICATION)
    if state == "verified" and not (how or "").strip():
        raise RecError("Say how you know: what you saw and where.")
    frm = rec.verification
    rec.verification, rec.verified_how, rec.verified_at = state, (how or "").strip() or None, _now() if state != "unverified" else None
    _log(db, rec, "verified", who, frm=frm, to=state, detail={"how": rec.verified_how})
    db.commit()
    db.refresh(rec)
    return rec


def record_follow_up(db: Session, rec: ConsultingRecommendation, who: str, note: str | None = None) -> ConsultingRecommendation:
    """The consultant followed up. Kept even when there was no reply, so the list of who to chase stays honest."""
    rec.last_follow_up_on = date.today()
    _log(db, rec, "note", who, detail={"follow_up": True, "note": note})
    db.commit()
    db.refresh(rec)
    return rec


def follow_ups(db: Session, client: Client, days: int = 14) -> list[ConsultingRecommendation]:
    """Published briefs nobody has reported on, handed off more than `days` ago and not chased within that time."""
    cutoff = _now() - timedelta(days=days)
    out = []
    for rec in db.query(ConsultingRecommendation).filter(ConsultingRecommendation.client_id == client.id, ConsultingRecommendation.review_state == "published").order_by(ConsultingRecommendation.published_at):
        if rec.impl_status in ("completed",) or rec.published_at is None or rec.published_at > cutoff:
            continue
        reported = rec.impl_updated_at is not None
        chased = rec.last_follow_up_on is not None and datetime.combine(rec.last_follow_up_on, datetime.min.time(), tzinfo=timezone.utc) > cutoff
        if not reported and not chased:
            out.append(rec)
    return out


def events(db: Session, rec: ConsultingRecommendation) -> list[ConsultingRecommendationEvent]:
    return db.query(ConsultingRecommendationEvent).filter(ConsultingRecommendationEvent.recommendation_id == rec.id).order_by(ConsultingRecommendationEvent.at.desc()).all()


def staff_out(rec: ConsultingRecommendation) -> dict[str, Any]:
    """Everything, for the consultant."""
    d = {c: getattr(rec, c) for c in (
        "title", "category", "focus", "source_kind", "source_ref", "finding", "explanation", "cause_kind", "cause_text", "action", "instructions", "target_urls", "priority",
        "expected_impact", "confidence", "confidence_reasons", "effort_min", "owner", "baseline", "success_metrics", "evidence", "internal_notes", "review_state", "revision",
        "impl_status", "impl_status_source", "implemented_on_estimated", "client_notes", "evidence_links", "verification", "verified_how", "created_by",
    )}
    for c in ("measure_on", "approved_at", "published_at", "archived_at", "impl_updated_at", "implemented_on", "last_follow_up_on", "verified_at", "created_at", "updated_at"):
        v = getattr(rec, c)
        d[c] = v.isoformat() if v else None
    d.update(id=str(rec.id), approved_by=rec.approved_by, published_by=rec.published_by, publish_gaps=publish_gaps(rec), next_states=list(TRANSITIONS[rec.review_state]))
    return d
