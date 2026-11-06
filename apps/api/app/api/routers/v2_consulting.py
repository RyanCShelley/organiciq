"""The consulting portal's API, and the consultant's workspace behind it.

Two kinds of route live here, on purpose apart from every internal router:
- the portal (`require_portal_access`): what a client's own team sees. It returns only what is written for them: no tier, allowance, integration or internal note.
- the workspace (`require_sma_staff`): the consultant's own notes and drafts.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.portal import CLIENT_ROLES, Portal, portal_clients, require_portal_access
from app.core.security import STAFF_ROLES, AuthUser, get_current_user, require_sma_staff
from app.models.user import UserRole
from app.models.client import Client
from app.models.consulting import ConsultingProfile
from app.services import consulting_recs, consulting_report, monthly_review

router = APIRouter(prefix="/v2/consulting", tags=["v2-consulting"])

BRAND = {"name": "SMA Marketing", "powered_by": "Organic IQ"}


def _site(c: Client) -> dict:
    """A site as the portal shows it: its name and address, never its plan or connections."""
    return {"id": str(c.id), "slug": c.slug, "name": c.client_name, "domain": c.domain, "group": c.group.name if c.group is not None else None}


@router.get("/clients")
def my_portals(
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """The portals this person may open."""
    return {"clients": [_site(c) for c in portal_clients(db, user)], "is_staff": user.role in STAFF_ROLES}


@router.get("/portal")
def portal(
    ctx: Annotated[Portal, Depends(require_portal_access)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """The front of one client's portal: who it is for, the company's other sites the viewer may open, and the brand it carries."""
    sites = [c for c in portal_clients(db, ctx.user) if ctx.client.group_id and c.group_id == ctx.client.group_id and c.id != ctx.client.id]
    return {"client": _site(ctx.client), "sites": [_site(c) for c in sites], "brand": BRAND, "previewing": ctx.is_staff}


FIELDS = ("goals", "primary_objective", "audiences", "markets", "priority_services", "constraints", "editorial_rules", "resources", "internal_notes")


class ProfileIn(BaseModel):
    ai_visibility_focus: bool = False
    goals: str | None = Field(default=None, max_length=8000)
    primary_objective: str | None = Field(default=None, max_length=4000)
    audiences: str | None = Field(default=None, max_length=8000)
    markets: str | None = Field(default=None, max_length=4000)
    priority_services: str | None = Field(default=None, max_length=8000)
    constraints: str | None = Field(default=None, max_length=8000)
    editorial_rules: str | None = Field(default=None, max_length=8000)
    resources: str | None = Field(default=None, max_length=8000)
    internal_notes: str | None = Field(default=None, max_length=12000)


def _profile_out(row: ConsultingProfile | None) -> dict:
    return {**{f: getattr(row, f) if row else None for f in FIELDS}, "ai_visibility_focus": bool(row.ai_visibility_focus) if row else False, "updated_by": row.updated_by if row else None, "updated_at": row.updated_at.isoformat() if row and row.updated_at else None}


@router.get("/profile")
def get_profile(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """What the consultant has written about this client's business (internal)."""
    return _profile_out(db.query(ConsultingProfile).filter(ConsultingProfile.client_id == client.id).one_or_none())


@router.put("/profile")
def save_profile(
    payload: ProfileIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    row = db.query(ConsultingProfile).filter(ConsultingProfile.client_id == client.id).one_or_none()
    if row is None:
        row = ConsultingProfile(client_id=client.id)
        db.add(row)
    for f in FIELDS:
        value = getattr(payload, f)
        setattr(row, f, (value or "").strip() or None)
    row.ai_visibility_focus = payload.ai_visibility_focus
    row.updated_by = user.email
    db.commit()
    db.refresh(row)
    return _profile_out(row)


# ── the consultant's briefs (staff only) ─────────────────────────────────────


def _rec(db: Session, client: Client, rec_id: UUID):
    rec = consulting_recs.get(db, client, rec_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That brief is not on this client.")
    return rec


def _full(db: Session, rec) -> dict:
    """The brief and its trail, as the editor shows them."""
    return {**consulting_recs.staff_out(rec), "events": [{"kind": e.kind, "from": e.from_value, "to": e.to_value, "by": e.by, "at": e.at.isoformat(), "detail": e.detail} for e in consulting_recs.events(db, rec)]}


def _guard(call):
    try:
        return call()
    except consulting_recs.RecConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except consulting_recs.RecError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


class RecIn(BaseModel):
    """Any of a brief's fields; what is left out is left as it was."""

    model_config = {"extra": "forbid"}

    title: str | None = Field(default=None, max_length=500)
    category: str | None = None
    focus: str | None = None
    source_kind: str | None = None
    source_ref: dict | None = None
    finding: str | None = Field(default=None, max_length=6000)
    explanation: str | None = Field(default=None, max_length=6000)
    cause_kind: str | None = None
    cause_text: str | None = Field(default=None, max_length=4000)
    action: str | None = Field(default=None, max_length=4000)
    instructions: list[Any] | None = None
    target_urls: list[Any] | None = None
    priority: str | None = None
    expected_impact: str | None = Field(default=None, max_length=2000)
    confidence: str | None = None
    confidence_reasons: list[str] | None = None
    effort_min: int | None = Field(default=None, ge=0, le=100000)
    owner: str | None = Field(default=None, max_length=120)
    baseline: list[Any] | None = None
    success_metrics: list[Any] | None = None
    measure_on: date | None = None
    evidence: list[Any] | None = None
    internal_notes: str | None = Field(default=None, max_length=12000)


class RecEdit(RecIn):
    revision: int


def _summary(rec) -> dict:
    full = consulting_recs.staff_out(rec)
    keep = ("id", "title", "category", "focus", "source_kind", "priority", "confidence", "review_state", "impl_status", "impl_status_source", "verification", "published_at", "revision", "updated_at", "last_follow_up_on")
    return {k: full[k] for k in keep}


@router.get("/recommendations")
def list_recommendations(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    state: Annotated[str | None, Query()] = None,
) -> dict:
    """The consultant's briefs, newest first, with how many are in each state."""
    from app.models.consulting import REVIEW_STATES, ConsultingRecommendation

    rows = db.query(ConsultingRecommendation).filter(ConsultingRecommendation.client_id == client.id).order_by(ConsultingRecommendation.updated_at.desc()).all()
    counts = {s: sum(1 for r in rows if r.review_state == s) for s in REVIEW_STATES}
    shown = [r for r in rows if not state or r.review_state == state]
    return {"counts": counts, "recommendations": [_summary(r) for r in shown], "follow_ups": len(consulting_recs.follow_ups(db, client))}


@router.post("/recommendations", status_code=status.HTTP_201_CREATED)
def create_recommendation(
    payload: RecIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return _full(db, _guard(lambda: consulting_recs.create(db, client, payload.model_dump(exclude_unset=True), user.email)))


@router.get("/recommendations/follow-ups")
def recommendation_follow_ups(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=120)] = 14,
) -> dict:
    """Published briefs handed off more than `days` ago that nobody has reported on and that have not been chased lately."""
    return {"days": days, "recommendations": [_summary(r) for r in consulting_recs.follow_ups(db, client, days)]}


@router.get("/recommendations/{rec_id}")
def get_recommendation(
    rec_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return _full(db, _rec(db, client, rec_id))


@router.patch("/recommendations/{rec_id}")
def edit_recommendation(
    rec_id: UUID,
    payload: RecEdit,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    rec = _rec(db, client, rec_id)
    data = payload.model_dump(exclude_unset=True)
    revision = data.pop("revision")
    return _full(db, _guard(lambda: consulting_recs.update(db, rec, data, revision, user.email)))


class StateIn(BaseModel):
    to: str


@router.post("/recommendations/{rec_id}/state")
def move_recommendation(
    rec_id: UUID,
    payload: StateIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Draft, under review, approved, published or archived. Publishing only makes the brief visible to the client: it creates no work for SMA."""
    rec = _rec(db, client, rec_id)
    return _full(db, _guard(lambda: consulting_recs.transition(db, rec, payload.to, user.email)))


class ProgressIn(BaseModel):
    status: str | None = None
    source: str = "consultant"
    implemented_on: date | None = None
    estimated: bool = False
    notes: str | None = Field(default=None, max_length=4000)
    links: list[str] | None = None


@router.post("/recommendations/{rec_id}/progress")
def record_recommendation_progress(
    rec_id: UUID,
    payload: ProgressIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """What the client's side did, as far as it is known: often the consultant recording what they were told."""
    rec = _rec(db, client, rec_id)
    return _full(db, _guard(lambda: consulting_recs.record_progress(
        db, rec, status=payload.status, source=payload.source, who=user.email, implemented_on=payload.implemented_on, estimated=payload.estimated, notes=payload.notes, links=payload.links)))


class VerifyIn(BaseModel):
    state: str
    how: str | None = Field(default=None, max_length=4000)


@router.post("/recommendations/{rec_id}/verify")
def verify_recommendation(
    rec_id: UUID,
    payload: VerifyIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    rec = _rec(db, client, rec_id)
    return _full(db, _guard(lambda: consulting_recs.record_verification(db, rec, payload.state, payload.how, user.email)))


class FollowUpIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


@router.post("/recommendations/{rec_id}/follow-up")
def follow_up_recommendation(
    rec_id: UUID,
    payload: FollowUpIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Note that the consultant followed up, even without a reply."""
    rec = _rec(db, client, rec_id)
    return _full(db, consulting_recs.record_follow_up(db, rec, user.email, payload.note))


# ── the client's portal: published briefs only ───────────────────────────────


@router.get("/portal/overview")
def portal_overview(
    ctx: Annotated[Portal, Depends(require_portal_access)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """The front page: how the published recommendations stand, and the most important ones still open."""
    return consulting_recs.overview(db, ctx.client)


@router.get("/portal/recommendations")
def portal_recommendations(
    ctx: Annotated[Portal, Depends(require_portal_access)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Every published recommendation, most urgent first. Nothing unpublished, and nothing internal, is in the reply."""
    return {"recommendations": [consulting_recs.client_out(r) for r in consulting_recs.published(db, ctx.client)], "can_update": ctx.is_staff or ctx.user.role == UserRole.CLIENT_ADMIN}


def _published(db: Session, client: Client, rec_id: UUID):
    rec = consulting_recs.get(db, client, rec_id)
    if rec is None or rec.review_state != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That recommendation is not available.")
    return rec


@router.get("/portal/recommendations/{rec_id}")
def portal_recommendation(
    rec_id: UUID,
    ctx: Annotated[Portal, Depends(require_portal_access)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return {**consulting_recs.client_out(_published(db, ctx.client, rec_id)), "can_update": ctx.is_staff or ctx.user.role == UserRole.CLIENT_ADMIN}


class ClientProgressIn(BaseModel):
    """All a client can change: where they are with it, when it went live, a note, and links that show it."""

    model_config = {"extra": "forbid"}

    status: str | None = None
    implemented_on: date | None = None
    estimated: bool = False
    notes: str | None = Field(default=None, max_length=4000)
    links: list[str] | None = None


@router.post("/portal/recommendations/{rec_id}/progress")
def portal_progress(
    rec_id: UUID,
    payload: ClientProgressIn,
    ctx: Annotated[Portal, Depends(require_portal_access)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Update where a recommendation stands. A client admin's update is recorded as the client's; a consultant's, made on their behalf, as the consultant's.

    It never verifies anything: only evidence does that.
    """
    if not (ctx.is_staff or ctx.user.role == UserRole.CLIENT_ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your access is read-only.")
    rec = _published(db, ctx.client, rec_id)
    source = "consultant" if ctx.is_staff else "client"
    done = _guard(lambda: consulting_recs.record_progress(db, rec, status=payload.status, source=source, who=ctx.user.email, implemented_on=payload.implemented_on, estimated=payload.estimated, notes=payload.notes, links=payload.links))
    return {**consulting_recs.client_out(done), "can_update": True}


# ── the report: Data, then the consultant's Analysis ─────────────────────────


def _month(value: str | None) -> str:
    return value or monthly_review.last_complete_month()


def _report_guard(call):
    try:
        return call()
    except consulting_report.ReportConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (consulting_report.ReportError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/report")
def get_report(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[str | None, Query()] = None,
) -> dict:
    """One month's report as the consultant works on it: their analysis so far, and the headline numbers as they stand now."""
    m = _month(month)
    rep = _report_guard(lambda: consulting_report.get(db, client, m))
    return {"report": consulting_report.staff_out(rep, m), "data": _report_guard(lambda: consulting_report.headline(db, client, m))}


class ReportIn(BaseModel):
    month: str
    analysis: str | None = Field(default=None, max_length=20000)
    title: str | None = Field(default=None, max_length=300)
    revision: int | None = None


@router.put("/report")
def save_report(
    payload: ReportIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    rep = _report_guard(lambda: consulting_report.save(db, client, payload.month, analysis=payload.analysis, title=payload.title, revision=payload.revision, who=user.email))
    return consulting_report.staff_out(rep, payload.month)


class ReportState(BaseModel):
    month: str
    to: str


@router.post("/report/state")
def move_report(
    payload: ReportState,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Publish the report to the client (freezing its numbers) or take it back to a draft."""
    rep = consulting_report.get(db, client, payload.month)
    if rep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Write and save your analysis first.")
    if payload.to == "published":
        rep = _report_guard(lambda: consulting_report.publish(db, client, rep, user.email))
    elif payload.to == "draft":
        rep = consulting_report.unpublish(db, rep)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A report is either published or a draft.")
    return consulting_report.staff_out(rep, payload.month)


@router.get("/portal/report")
def portal_report(
    ctx: Annotated[Portal, Depends(require_portal_access)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """The latest published report: the numbers as they were when it was published, and the consultant's analysis. None until one is published."""
    rep = consulting_report.latest_published(db, ctx.client)
    return {"report": consulting_report.client_out(rep) if rep else None}
