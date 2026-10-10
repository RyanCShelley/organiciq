from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_admin, require_sma_staff
from app.core.settings import get_settings
from app.integrations import teamwork
from app.services import page_stage
from app.services.triage_signals import NEXT_STEP_COVERAGE_FLOOR
from app.models.client import Client
from app.models.decision import DecisionStatus, EngineAction
from app.schemas import (
    EngineActionAssign,
    EngineActionSkip,
    MonthlyRunRequest,
    PageStageIn,
    KeywordTargetOut,
    KeywordTargetUpdate,
    DecisionEnsureRequest,
    DecisionEvaluateRequest,
    DecisionEvaluateResponse,
    DecisionOut,
    DecisionStatusUpdate,
    DecisionThresholdsOut,
    DecisionThresholdsUpdate,
    DiagnoseResponse,
)
from app.services import decisions as decision_service
from app.services import engine_actions as engine_action_service
from app.services.decisions import upsert_keyword_page_map
from app.services.decision_serialization import serialize_diagnose
from app.services.monthly_run import latest_record, save_record

router = APIRouter(prefix="/decisions", tags=["decisions"])


def _serialize_diagnose(result) -> DiagnoseResponse:
    return serialize_diagnose(result)


@router.get("/diagnose", response_model=DiagnoseResponse)
def diagnose_client(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    from_date: Annotated[date, Query(alias="from")],
    to_date: Annotated[date, Query(alias="to")],
) -> DiagnoseResponse:
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'from' must be on or before 'to'",
        )
    result = decision_service.run_diagnose(db, client, from_date=from_date, to_date=to_date)
    return _serialize_diagnose(result)


@router.get("", response_model=list[DecisionOut])
def list_decisions(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    from_date: Annotated[date | None, Query(alias="from")] = None,
    to_date: Annotated[date | None, Query(alias="to")] = None,
) -> list[DecisionOut]:
    rows = decision_service.list_decisions(
        db,
        client.id,
        from_date=from_date,
        to_date=to_date,
    )
    return [DecisionOut.model_validate(row) for row in rows]


@router.post("/evaluate", response_model=DecisionEvaluateResponse)
def evaluate_decisions(
    payload: DecisionEvaluateRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> DecisionEvaluateResponse:
    if payload.from_date > payload.to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'from' must be on or before 'to'",
        )
    created, skipped, result = decision_service.evaluate_and_store(
        db,
        client,
        from_date=payload.from_date,
        to_date=payload.to_date,
    )
    return DecisionEvaluateResponse(
        created=[DecisionOut.model_validate(row) for row in created],
        skipped=skipped,
        diagnose=_serialize_diagnose(result),
    )


@router.post("/ensure", response_model=DecisionOut)
def ensure_decision(
    payload: DecisionEnsureRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> DecisionOut:
    """Create (or return) a stored decision for any finding rule_key, including additional findings."""
    if payload.from_date > payload.to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'from' must be on or before 'to'",
        )
    rule_key = payload.rule_key.strip()
    if not rule_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rule_key is required")
    decision = decision_service.ensure_decision_for_rule(
        db,
        client,
        from_date=payload.from_date,
        to_date=payload.to_date,
        rule_key=rule_key,
    )
    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Finding not found for this period (or Decision Engine not ready).",
        )
    return DecisionOut.model_validate(decision)


@router.patch("/{decision_id}", response_model=DecisionOut)
def update_decision(
    decision_id: UUID,
    payload: DecisionStatusUpdate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> DecisionOut:
    try:
        new_status = DecisionStatus(payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc

    updated = decision_service.update_decision_status(
        db,
        client_id=client.id,
        decision_id=decision_id,
        status=new_status,
        dismissal_reason=payload.dismissal_reason,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    return DecisionOut.model_validate(updated)


@router.get("/thresholds", response_model=DecisionThresholdsOut)
def get_thresholds(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> DecisionThresholdsOut:
    return DecisionThresholdsOut(
        thresholds=decision_service.get_thresholds(db, client.id),
        defaults=decision_service.default_threshold_catalog(),
    )


@router.put("/thresholds", response_model=DecisionThresholdsOut)
def put_thresholds(
    payload: DecisionThresholdsUpdate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> DecisionThresholdsOut:
    merged = decision_service.upsert_thresholds(db, client.id, payload.thresholds)
    return DecisionThresholdsOut(
        thresholds=merged,
        defaults=decision_service.default_threshold_catalog(),
    )


@router.get("/keyword-page-map")
def get_keyword_page_map(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Every tracked keyword with its mapping, plus the pages to choose from."""
    return decision_service.keyword_page_map_view(db, client.id)


@router.put("/keyword-page-map", response_model=list[KeywordTargetOut])
def put_keyword_page_map(
    payload: KeywordTargetUpdate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[KeywordTargetOut]:
    """Record which page owns a term.

    A row with no page_url means "no page owns this yet", which is an
    answer and stops the engine asking again.
    """
    rows = upsert_keyword_page_map(db, client.id, payload.entries)
    return [KeywordTargetOut.model_validate(row) for row in rows]


@router.get("/records")
def list_monthly_records(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    """The months this client has a saved run for, newest first.

    The page offers these in a Run selector instead of a date picker. A date
    picker invites a reader to ask for a window the engine never ran, and
    then recomputes one on the spot — which is how the same page said
    different things on the same day.
    """
    from app.models.decision import MonthlyRecord

    rows = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.client_id == client.id)
        .order_by(MonthlyRecord.month.desc())
        .all()
    )
    return [
        {
            "month": row.month,
            "run_saved_at": row.run_saved_at.isoformat() if row.run_saved_at else None,
            "data_through": row.data_through.isoformat() if row.data_through else None,
            "constraint": row.constraint_name,
            "confidence": row.confidence,
        }
        for row in rows
    ]


@router.get("/records/{month}")
def get_monthly_record(
    month: str,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """One saved record. The page renders this and recomputes nothing."""
    from app.models.decision import MonthlyRecord

    row = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.client_id == client.id, MonthlyRecord.month == month)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No saved run for {month}.",
        )
    return row.record


@router.get("/records/latest/current")
def get_latest_record(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    row = latest_record(db, client)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This client has no saved run yet.",
        )
    return row.record


@router.post("/records/run", status_code=status.HTTP_201_CREATED)
def run_monthly(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
    payload: MonthlyRunRequest | None = None,
) -> dict:
    """Run a month and replace its record. Admin only.

    `month` picks which one. A month is normally reviewed once it has
    finished, so running November's engine over October's data is the common
    case rather than the exception; without it the only month anybody could
    run was the one they were standing in, measured to whatever day that
    happened to be.
    """
    month = (payload.month if payload else None) or None
    try:
        return save_record(db, client, month=month).record
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


# ── The workflow beside the record ──────────────────────────────────────────
#
# The saved record is what the engine decided and never changes here. These
# endpoints own the other half — who the slot went to, whether it was skipped,
# whether it was pushed to Teamwork — in `engine_actions`.


def _slot_or_404(db: Session, client: Client, month: str, uid: str):
    record = engine_action_service.load_record(db, client, month)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No saved run for {month}.",
        )
    slots = engine_action_service.slots_in_record(record.record)
    slot = slots.get(uid)
    if slot is None:
        # Without this the endpoint is an open write to a table keyed by a
        # string the caller chooses.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{uid} is not a slot in the {month} run.",
        )
    return record, slot


@router.get("/records/{month}/workflow")
def get_workflow(
    month: str,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """What the team has done about this month's slots.

    Served apart from the record so that assigning a task never rewrites what
    the engine decided.
    """
    record = engine_action_service.load_record(db, client, month)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No saved run for {month}.",
        )
    slots = engine_action_service.slots_in_record(record.record)
    rows = engine_action_service.list_workflow(db, client, month)
    return {
        "month": month,
        "teamwork_ready": teamwork.configured() and bool(client.teamwork_tasklist_id),
        "actions": [
            engine_action_service.serialise(row, slot=slots.get(row.uid)) for row in rows
        ],
    }


@router.get("/assignees")
def list_assignees(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    """Who can be given work on this client.

    Admins are included because they can see every client without an
    assignment; leaving them out would make the list read as "nobody".
    """
    from app.models.user import User, UserClient, UserRole

    out: list[dict] = []
    seen: set[UUID] = set()
    for user in (
        db.query(User)
        .filter(User.role == UserRole.SMA_ADMIN, User.is_active.is_(True))
        .order_by(User.email.asc())
        .all()
    ):
        seen.add(user.id)
        out.append({"user_id": str(user.id), "email": user.email, "name": user.name})

    assigned = (
        db.query(User)
        .join(UserClient, UserClient.user_id == User.id)
        .filter(UserClient.client_id == client.id, User.is_active.is_(True))
        .order_by(User.email.asc())
        .all()
    )
    for user in assigned:
        if user.id in seen:
            continue
        seen.add(user.id)
        out.append({"user_id": str(user.id), "email": user.email, "name": user.name})
    return out


@router.post("/records/{month}/slots/{uid}/assign")
def assign_slot(
    month: str,
    uid: str,
    payload: EngineActionAssign,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _, slot = _slot_or_404(db, client, month, uid)
    row = engine_action_service.assign(
        db,
        client,
        slot,
        month,
        assignee_user_id=payload.assignee_user_id,
        due=payload.due,
    )
    db.commit()
    return engine_action_service.serialise(row, slot=slot)


@router.post("/records/{month}/slots/{uid}/skip")
def skip_slot(
    month: str,
    uid: str,
    payload: EngineActionSkip,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _, slot = _slot_or_404(db, client, month, uid)
    try:
        row = (
            engine_action_service.unskip(db, client, slot, month)
            if payload.undo
            else engine_action_service.skip(db, client, slot, month, reason=payload.reason or "")
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    db.commit()
    return engine_action_service.serialise(row, slot=slot)


@router.post("/records/{month}/slots/{uid}/send")
def send_slot(
    month: str,
    uid: str,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Push the slot to Teamwork as a task.

    Idempotent by the stored task id: a second press links to the task that
    exists rather than creating a twin.
    """
    record, slot = _slot_or_404(db, client, month, uid)
    existing = (
        db.query(EngineAction)
        .filter(EngineAction.client_id == client.id, EngineAction.uid == uid)
        .one_or_none()
    )
    if existing is not None and existing.teamwork_task_id:
        return engine_action_service.serialise(existing, slot=slot)

    name, description = teamwork.task_body(
        title=slot.title,
        why=slot.why,
        done_when=slot.done_when,
        target_url=slot.target_url,
        metric=slot.metric,
        check_on=slot.check_on,
        effort_min=slot.effort_min,
        record_url=f"{get_settings().web_app_url}/{client.slug}/decision-engine?run={month}",
    )
    try:
        created = teamwork.create_task(
            tasklist_id=client.teamwork_tasklist_id or "",
            name=name,
            description=description,
            due=existing.due.isoformat() if existing is not None and existing.due else None,
        )
    except teamwork.TeamworkError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    row = engine_action_service.mark_sent(
        db, client, slot, month, task_id=created["id"], task_url=created["url"]
    )
    db.commit()
    return engine_action_service.serialise(row, slot=slot)


# ── Funnel stage on landing pages ───────────────────────────────────────────
#
# L3's missing third input. A model proposes, a person confirms, and only the
# confirmed stage is read by the engine — the same shape as conversion
# definitions and conversion pages, for the same reason.


@router.get("/page-stages")
def list_page_stages(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """The landing pages worth labelling, busiest first.

    Carries the sessions each page drew and the share already confirmed, so
    the screen can say how much of the traffic is covered rather than how many
    rows are ticked. Thirty rows covering 5% of sessions is not progress.
    """
    from app.models.config import ClientPageStage

    candidates = page_stage.load_candidates(db, client)
    stored = {
        row.normalized_url: row
        for row in db.query(ClientPageStage).filter(
            ClientPageStage.client_id == client.id
        )
    }

    total_sessions = sum(c.sessions for c in candidates) or 0.0
    confirmed_sessions = sum(
        c.sessions
        for c in candidates
        if (row := stored.get(c.normalized_url)) is not None and row.confirmed_at
    )

    return {
        "model_ready": page_stage.configured(),
        "coverage": {
            "pages": len(candidates),
            "confirmed_pages": sum(
                1
                for c in candidates
                if (row := stored.get(c.normalized_url)) is not None and row.confirmed_at
            ),
            "sessions": total_sessions,
            "confirmed_sessions": confirmed_sessions,
            "floor": NEXT_STEP_COVERAGE_FLOOR,
        },
        "pages": [
            {
                "normalized_url": c.normalized_url,
                "title": c.title,
                "sessions": c.sessions,
                "stage": (row := stored.get(c.normalized_url)) and row.stage,
                "suggested_stage": row and row.suggested_stage,
                "confidence": row and row.confidence,
                "rationale": row and row.rationale,
                "confirmed": bool(row and row.confirmed_at),
            }
            for c in candidates
        ],
    }


@router.post("/page-stages/suggest")
def suggest_page_stages(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Ask the model to read the pages and propose a stage for each.

    Suggestions never overwrite a confirmed stage: re-running this must not
    revise an answer somebody already agreed to.
    """
    classifier = page_stage.load_classifier()
    if classifier is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No model is configured for this. Set ANTHROPIC_API_KEY to let "
                "it read the pages, or set the stages by hand."
            ),
        )
    candidates = page_stage.load_candidates(db, client)
    if not candidates:
        return {"suggested": 0, "pages": 0}
    try:
        suggestions = classifier.classify(candidates)
    except page_stage.NotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    written = page_stage.save_suggestions(
        db, client, suggestions, model=classifier.name
    )
    return {"suggested": written, "pages": len(candidates)}


@router.put("/page-stages")
def confirm_page_stages(
    payload: list[PageStageIn],
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Record the stages somebody agreed to. These are what the engine reads."""
    written = page_stage.confirm(
        db,
        client,
        [(entry.normalized_url, entry.stage) for entry in payload],
        user_id=user.id,
    )
    return {"confirmed": written}
