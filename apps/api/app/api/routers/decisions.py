from __future__ import annotations

import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_admin, require_sma_staff
from app.core.settings import get_settings
from app.integrations import teamwork
from app.schemas.plan_review import MeasurementSettings
from app.services import page_stage
from app.services import portfolio as portfolio_service
from app.services.triage_signals import NEXT_STEP_COVERAGE_FLOOR
from app.models.client import Client
from app.models.decision import EngineAction, ExcludedPage
from app.schemas.plan_review import PlanReviewUpdate, PlanApproval
from app.schemas.watchlist import WatchTargetUpdate
from app.schemas import (
    EngineActionAssign,
    EngineActionInPlan,
    EngineActionShipped,
    ExcludedPageIn,
    EngineActionSkip,
    MonthlyRunRequest,
    PageStageIn,
    KeywordTargetOut,
    KeywordTargetUpdate,
)
from app.services import decisions as decision_service
from app.services import engine_actions as engine_action_service
from app.services.decisions import upsert_keyword_page_map
from app.services.monthly_run import _previous_month, month_key, save_record

logger = logging.getLogger("organiciq.decisions")

router = APIRouter(prefix="/decisions", tags=["decisions"])

@router.get("/watchlist")
def get_watchlist(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    from app.services.watchlist import read
    return read(db, client)


@router.put("/watchlist")
def put_watchlist(
    payload: WatchTargetUpdate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    from app.services.watchlist import write
    return write(db, client, payload)


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


@router.get("/portfolio")
def get_portfolio(
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
) -> dict:
    """Every client's month on one screen.

    Portfolio-wide, so it takes no client header — but it is filtered to the
    clients the caller can see. An admin sees all of them; anybody else sees
    the ones they are assigned, because a staff list of every client's
    constraint is a different thing from the client they were given.
    """
    from app.models.user import UserClient, UserRole

    allowed: set[str] | None = None
    if user.role != UserRole.SMA_ADMIN:
        allowed = {
            str(row.client_id)
            for row in db.query(UserClient).filter(UserClient.user_id == user.id)
        }
    return portfolio_service.portfolio(db, month=month, allowed_client_ids=allowed)


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


@router.get("/measurement-settings")
def get_measurement_settings(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    from app.services.decision_measurements import lead_rate_target
    from app.models.config import ClientConversionPage
    return {"target_lead_rate_pct": lead_rate_target(db, client.id),
            "conversion_page_count": db.query(ClientConversionPage).filter_by(client_id=client.id).count()}


@router.put("/measurement-settings")
def put_measurement_settings(
    payload: "MeasurementSettings",
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    from app.models.decision import DecisionThreshold
    row = db.query(DecisionThreshold).filter_by(client_id=client.id).with_for_update().one_or_none()
    if row is None:
        row = DecisionThreshold(client_id=client.id, thresholds={})
        db.add(row)
    row.thresholds = {**(row.thresholds or {}), "target_lead_rate_pct": payload.target_lead_rate_pct}
    db.commit()
    return {"target_lead_rate_pct": payload.target_lead_rate_pct}


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
    from app.decisions.planning import effective_record
    result = effective_record(row.record)
    if "measurements" not in result:
        # Production already has saved assessments. Populate their new display
        # from stored facts without rerunning integrations or rewriting history.
        import calendar
        from app.services.decision_measurements import measure
        year, month_number = map(int, row.month.split("-"))
        end = date(year, month_number, calendar.monthrange(year, month_number)[1])
        result["measurements"] = measure(db, client, end=end)
        result["measurements"]["source_note"] = "Measured from currently stored facts for this assessment period. Saved recommendations and approval history are unchanged."
    return result


@router.get("/records/{month}/review")
def get_plan_review(
    month: str,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    from app.services import plan_review
    row = engine_action_service.load_record(db, client, month)
    if row is None:
        raise HTTPException(404, "No saved run for this month.")
    return plan_review.view(row)


@router.put("/records/{month}/review")
def put_plan_review(
    month: str, payload: PlanReviewUpdate,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    from app.services import plan_review
    row = plan_review.locked_record(db, client, month)
    if row is None:
        raise HTTPException(404, "No saved run for this month.")
    try:
        return plan_review.save(db, row, payload, user)
    except plan_review.ReviewConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/records/{month}/review/approve")
def approve_plan_review(
    month: str, payload: PlanApproval,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    from app.services import plan_review
    row = plan_review.locked_record(db, client, month)
    if row is None:
        raise HTTPException(404, "No saved run for this month.")
    try:
        return plan_review.approve(db, row, payload.revision, user)
    except plan_review.ReviewConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


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
    this_month = month_key(date.today())
    month = (payload.month if payload else None) or _previous_month(this_month)
    if month >= this_month:
        # The engine needs the whole month, and its record is the plan for the
        # month after. A run made mid-month is a partial run filed as a month.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Run a month after it has finished: the engine needs the whole month's data.",
        )
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
    from app.services.plan_review import locked_record
    record = locked_record(db, client, month)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No saved run for {month}.",
        )
    from app.services.plan_review import workflow_record
    slots = engine_action_service.slots_in_record(workflow_record(record.record))
    slot = slots.get(uid)
    if slot is None:
        # Without this the endpoint is an open write to a table keyed by a
        # string the caller chooses.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{uid} is not a slot in the {month} run.",
        )
    return record, slot


def _require_reviewed_growth(record, slot):
    if slot.kind == "action" and (record.record.get("review_required") or record.record.get("plan_review")):
        review = record.record.get("plan_review") or {}
        if not review.get("approved_at") or slot.uid not in {x["action_uid"] for x in review.get("items", [])}:
            raise HTTPException(422, "Approve the reviewed plan before assigning or delivering growth work.")


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
    from app.services.plan_review import workflow_record
    slots = engine_action_service.slots_in_record(workflow_record(record.record))
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
    """Who can be given work.

    Teamwork's people where it is connected, because that is who does the
    work: most of the team never opens this tool, and listing only the
    accounts that can sign in here left four of eight unassignable. Falls
    back to OrganicIQ staff so the dropdown is never empty.
    """
    from app.models.user import User, UserClient, UserRole

    if teamwork.configured():
        try:
            return [
                {"email": p.email, "name": p.name, "source": "teamwork"}
                for p in sorted(teamwork.list_people(), key=lambda p: p.name.lower())
            ]
        except teamwork.TeamworkError:
            logger.warning("Could not read Teamwork people; falling back to staff")

    out: list[dict] = []
    seen: set[str] = set()
    for user in (
        db.query(User)
        .filter(User.role == UserRole.SMA_ADMIN, User.is_active.is_(True))
        .order_by(User.email.asc())
    ):
        seen.add(user.email.lower())
        out.append({"email": user.email, "name": user.name or user.email,
                    "source": "organiciq"})
    for user in (
        db.query(User)
        .join(UserClient, UserClient.user_id == User.id)
        .filter(UserClient.client_id == client.id, User.is_active.is_(True))
        .order_by(User.email.asc())
    ):
        if user.email.lower() in seen:
            continue
        seen.add(user.email.lower())
        out.append({"email": user.email, "name": user.name or user.email,
                    "source": "organiciq"})
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
    from app.models.user import User

    record, slot = _slot_or_404(db, client, month, uid)
    _require_reviewed_growth(record, slot)
    email = (payload.assignee_email or "").strip().lower() or None
    account = (
        db.query(User).filter(func.lower(User.email) == email).one_or_none()
        if email
        else None
    )
    row = engine_action_service.assign(
        db,
        client,
        slot,
        month,
        assignee_email=email,
        assignee_name=payload.assignee_name or (account.name if account else None),
        due=payload.due,
        db_user_id=account.id if account else None,
    )
    db.commit()
    return engine_action_service.serialise(row, slot=slot)


@router.post("/records/{month}/slots/{uid}/in-plan")
def set_slot_in_plan(
    month: str,
    uid: str,
    payload: EngineActionInPlan,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Put an action in the month's plan, or take it out.

    The engine ranks and fills the slots; it does not know the team is on a
    larger project this month. Sending `null` hands the decision back rather
    than freezing whatever the engine last said.
    """
    record, slot = _slot_or_404(db, client, month, uid)
    if slot.kind == "action" and record.record.get("plan_review"):
        raise HTTPException(422, "Edit the reviewed plan to change selected growth work.")
    if slot.kind in ("update", "content"):
        from app.decisions.planning import page_identity
        data = record.record
        pool, candidate_pool, allowance_key = (
            ("updates", "update_candidates", "update_slots") if slot.kind == "update"
            else ("new_content", "content_candidates", "content_slots")
        )
        defaults = {x["action_uid"] for x in data.get(pool, [])}
        selecting = payload.in_plan if payload.in_plan is not None else uid in defaults
        if selecting:
            review = data.get("plan_review") or {}
            approved = review if review.get("approved_at") else next(iter(reversed(review.get("versions", []))), {})
            if slot.target_url and page_identity(slot.target_url) in {page_identity(x["target_url"]) for x in approved.get("items", [])}:
                raise HTTPException(422, "This page already has an approved growth brief. Combine the work in the reviewed plan.")
            states = {x.uid: x for x in engine_action_service.list_workflow(db, client, month)}
            active = set()
            for item in [*data.get(pool, []), *data.get(candidate_pool, [])]:
                item_uid = item["action_uid"]
                state = states.get(item_uid)
                chosen = state.in_plan if state and state.in_plan is not None else item_uid in defaults
                if chosen and (not state or state.status != "skipped"):
                    active.add(item_uid)
            active.add(uid)
            if allowance_key in data and len(active) > data[allowance_key]:
                raise HTTPException(422, "Remove another item before exceeding this pool's allowance.")
    row = engine_action_service.set_in_plan(
        db, client, slot, month, in_plan=payload.in_plan, reason=payload.reason
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


@router.post("/records/{month}/slots/{uid}/shipped")
def ship_slot(
    month: str,
    uid: str,
    payload: EngineActionShipped,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Record when the work went live, which is what the results loop reads."""
    record, slot = _slot_or_404(db, client, month, uid)
    _require_reviewed_growth(record, slot)
    row = engine_action_service.mark_shipped(
        db, client, slot, month, on=payload.shipped_on
    )
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
    _require_reviewed_growth(record, slot)
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
    if slot.steps:
        description += "\n\nChecklist\n" + "\n".join(f"{i + 1}. {step}" for i, step in enumerate(slot.steps))
    if slot.evidence:
        description += "\n\nEvidence and limitations\n" + "\n".join(slot.evidence)
    if slot.check_after_days:
        description += f"\n\nEvaluate {slot.check_after_days} days after recorded shipment."
    # Whoever holds the slot here should hold the task there. Matched on
    # email rather than through a mapping somebody has to maintain — the
    # addresses are the same in both systems. No match means the task is
    # created unassigned rather than not created.
    assignee_teamwork_id: str | None = None
    if existing is not None and existing.assignee_email:
        try:
            assignee_teamwork_id = teamwork.person_id_for(
                existing.assignee_email, teamwork.list_people()
            )
        except teamwork.TeamworkError:
            logger.warning("Could not read Teamwork people; sending %s unassigned", uid)

    try:
        created = teamwork.create_task(
            tasklist_id=client.teamwork_tasklist_id or "",
            name=name,
            description=description,
            due=existing.due.isoformat() if existing is not None and existing.due else None,
            assignee_teamwork_id=assignee_teamwork_id,
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
    # A confirmed stage is final, so there is nothing to suggest for it. The
    # model was being sent every page and the answers for confirmed ones thrown
    # away — billed per page, batched in twenties, inside this request.
    confirmed = page_stage.confirmed_stages(db, client.id)
    to_read = [c for c in candidates if c.normalized_url not in confirmed]
    if not to_read:
        return {"suggested": 0, "pages": len(candidates), "already_confirmed": len(candidates)}
    try:
        suggestions = classifier.classify(to_read)
    except page_stage.NotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    written = page_stage.save_suggestions(
        db, client, suggestions, model=classifier.name
    )
    return {
        "suggested": written,
        "pages": len(candidates),
        "already_confirmed": len(candidates) - len(to_read),
    }


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


# ── Pages the engine must leave alone ───────────────────────────────────────
#
# The table has existed since the engine did and nothing could write to it,
# so "we are not working on careers" was a thing somebody could say and not
# record. Boys Electrical's only traffic action was on /careers.


@router.get("/teamwork/tasklists")
def list_teamwork_tasklists(
    _: Annotated[AuthUser, Depends(require_sma_staff)],
) -> dict:
    """The tasklists this token can see, so a client can be pointed at one.

    Typing an id read off a URL is how a task ends up in the wrong client's
    list, and nothing downstream would catch it.
    """
    if not teamwork.configured():
        return {"configured": False, "tasklists": [], "error": None}
    try:
        found = teamwork.list_tasklists()
    except teamwork.TeamworkError as exc:
        return {"configured": True, "tasklists": [], "error": str(exc)}
    return {
        "configured": True,
        "error": None,
        "tasklists": [
            {
                "id": row.id,
                "name": row.name,
                "project_id": row.project_id,
                "project_name": row.project_name,
            }
            for row in found
        ],
    }


@router.post("/keyword-suggestions/run")
def run_keyword_suggestions(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Match every tracked term to a page by subject, and store what clears
    this client's margin.

    Synchronous because somebody pressed a button and is waiting: it reads
    the newest crawl, so it is the same work whenever it runs, and the model
    is loaded in-process. Tens of seconds on a large site.
    """
    from app.services.keyword_matcher import refresh_for

    try:
        found = refresh_for(db, client)
    except Exception as exc:  # noqa: BLE001 — a model failure is not a 500 page
        logger.exception("Keyword matching failed for %s", client.slug)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The matcher did not finish: {exc}"[:300],
        ) from exc

    from app.services.automatic_keyword_map import build as build_map
    found["map"] = build_map(db, client)
    db.commit()

    if not found["pages"]:
        return {**found, "reason": "No crawled page has a title or headings to read."}
    if not found["terms"]:
        return {**found, "reason": "No tracked keywords to match."}
    return found


@router.get("/excluded-pages")
def list_excluded_pages(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    return [
        {"url_pattern": row.url_pattern, "reason": row.reason}
        for row in db.query(ExcludedPage)
        .filter(ExcludedPage.client_id == client.id)
        .order_by(ExcludedPage.url_pattern)
    ]


@router.put("/excluded-pages")
def replace_excluded_pages(
    payload: list[ExcludedPageIn],
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    """Replace the whole list, because that is how the panel edits it.

    A reason is required. An excluded page with no reason is a rule nobody
    can review later, and next year nobody will remember why the engine
    stopped looking at a section of the site.
    """
    seen: set[str] = set()
    cleaned: list[tuple[str, str]] = []
    for entry in payload:
        pattern = entry.url_pattern.strip()
        reason = entry.reason.strip()
        if not pattern:
            continue
        if not reason:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{pattern} needs a reason.",
            )
        if pattern in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{pattern} is listed twice",
            )
        seen.add(pattern)
        cleaned.append((pattern, reason))

    db.query(ExcludedPage).filter(ExcludedPage.client_id == client.id).delete(
        synchronize_session=False
    )
    for pattern, reason in cleaned:
        db.add(
            ExcludedPage(client_id=client.id, url_pattern=pattern, reason=reason)
        )
    db.commit()
    return list_excluded_pages(client=client, _=_, db=db)
