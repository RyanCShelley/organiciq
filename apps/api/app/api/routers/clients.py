from datetime import date as DateType
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.client_scope import require_client, user_can_access_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_admin, require_sma_staff
from app.models.client import Client
from app.models.user import UserRole
from app.schemas import (
    BaselineGoalRequest,
    BaselineLeadConversionsRequest,
    BaselineLockRequest,
    BaselineSeriesCsvRequest,
    BaselineSnapshotApplyRequest,
    BaselineSnapshotPreviewOut,
    ClientCreate,
    ClientOut,
    ClientUpdate,
)
from app.services import baseline_lock, baseline_series, baseline_snapshot, clients as client_service, lead_conversions

from app.services.plan_allowances import resolve_plan_allowances

from app.services.client_setup import setup_state

router = APIRouter(prefix="/clients", tags=["clients"])


def client_out(client: Client) -> ClientOut:
    """A client with its plan allowance already worked out.

    The number is a business rule about what the client is buying, so the
    server answers it. The web used to apply the rule itself, which meant
    fetching `/admin/tiers` — an endpoint a client-role user is forbidden
    to call, so the whole Decision Engine page failed for them.
    """
    out = ClientOut.model_validate(client)
    if client.tier is not None:
        allowances = resolve_plan_allowances(client, client.tier)
        out.growth_action_allowance = allowances.growth_action_allowance
        out.plan_label = f"{allowances.tier_name} plan"
    return out



@router.get("", response_model=list[ClientOut])
def list_clients(
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ClientOut]:
    return [client_out(c) for c in client_service.list_clients(db, user)]


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ClientOut:
    client = client_service.create_client(db, payload)
    return client_out(client)


@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: UUID,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> ClientOut:
    if not user_can_access_client(db, user, client_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this client")
    client = client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client_out(client)


#: What a client is sold and what it may spend. Any staff member assigned to a
#: client could change these, including their own spend ceilings: the plan tier,
#: the custom allowances, and the crawl and AI-search limits that decide how
#: many pages are fetched and how many billed prompts are run. The settings
#: form sends every field on every save, so only a *change* is refused — saving
#: the other fields with these untouched still works.
ADMIN_ONLY_FIELDS = (
    "tier_id",
    "custom_tracked_keyword_limit",
    "custom_tracked_prompt_limit",
    "custom_content_allowance",
    "custom_update_allowance",
    "custom_growth_action_allowance",
    "custom_watchlist_cadence",
    "ai_search_prompt_limit",
    "crawl_page_limit",
)


def changed_admin_only_fields(client, payload: ClientUpdate) -> list[str]:
    sent = payload.model_dump(exclude_unset=True)
    return [
        name
        for name in ADMIN_ONLY_FIELDS
        if name in sent and sent[name] != getattr(client, name, None)
    ]


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: UUID,
    payload: ClientUpdate,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> ClientOut:
    if not user_can_access_client(db, user, client_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this client")
    client = client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    if user.role != UserRole.SMA_ADMIN:
        changed = changed_admin_only_fields(client, payload)
        if changed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Only an SMA admin can change: {', '.join(changed)}",
            )
    updated = client_service.update_client(db, client, payload)
    return client_out(updated)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_client(
    client_id: UUID,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    if not client_service.delete_client(db, client_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{client_id}/setup")
def client_setup(
    client_id: UUID,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """What is set up for this client and what has to happen next.

    Measured from the data on every request rather than stored. A saved
    "step 4 complete" would outlive the thing it describes the moment somebody
    deletes a conversion definition.
    """
    if not user_can_access_client(db, user, client_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this client"
        )
    client = client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return setup_state(db, client)


@router.get("/{client_id}/baseline/preview", response_model=BaselineSnapshotPreviewOut)
def preview_baseline_from_ga4(
    client_id: UUID,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    as_of: DateType | None = Query(default=None),
    lookback_days: int = Query(default=90, ge=7, le=365),
) -> BaselineSnapshotPreviewOut:
    if not user_can_access_client(db, user, client_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this client")
    client = client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    try:
        preview = baseline_snapshot.preview_baseline_from_ga4(
            db, client, as_of=as_of, lookback_days=lookback_days
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BaselineSnapshotPreviewOut.model_validate(preview)


def _staff_client(db: Session, user: AuthUser, client_id: UUID) -> Client:
    if not user_can_access_client(db, user, client_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this client")
    client = client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


@router.get("/{client_id}/baseline/series")
def baseline_series_from_ga4(
    client_id: UUID,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    months: int = Query(default=24, ge=6, le=48),
    regime_start: str | None = Query(default=None),
    half_life_months: float = Query(default=3.0, ge=0.5, le=24),
    lead_event: list[str] = Query(default=[]),
    acknowledge: list[str] = Query(default=[]),
) -> dict:
    """The recent-window baseline, ranges and flags from the synced GA4 data. Writes nothing."""
    client = _staff_client(db, user, client_id)
    try:
        return baseline_series.build_result(
            db,
            client,
            source="ga4",
            regime_start=regime_start,
            lead_events=lead_event or None,
            half_life_months=half_life_months,
            acknowledged=acknowledge,
            months=months,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{client_id}/baseline/series")
def baseline_series_from_csv(
    client_id: UUID,
    payload: BaselineSeriesCsvRequest,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """The same baseline from a pasted monthly CSV. Writes nothing."""
    client = _staff_client(db, user, client_id)
    try:
        return baseline_series.build_result(
            db,
            client,
            source="csv",
            csv_text=payload.csv_text,
            regime_start=payload.regime_start,
            half_life_months=payload.half_life_months,
            acknowledged=payload.acknowledged,
            as_of=payload.as_of,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{client_id}/baseline/events")
def baseline_lead_event_candidates(
    client_id: UUID,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """The events this client's GA4 has sent, for choosing which count as leads."""
    client = _staff_client(db, user, client_id)
    return baseline_series.lead_event_candidates(db, client)


@router.post("/{client_id}/baseline/lead-conversions")
def set_lead_conversions(
    client_id: UUID,
    payload: BaselineLeadConversionsRequest,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Make these exactly the client's lead conversions, so the baseline and the home screen agree.

    Nothing is deleted: a definition that drops out is switched off.
    """
    client = _staff_client(db, user, client_id)
    changes = lead_conversions.sync(db, client.id, payload.lead_events)
    db.commit()
    return {"changes": changes, "lead_events": lead_conversions.active_lead_events(db, client.id)}


@router.post("/{client_id}/baseline/goal")
def set_baseline_goal(
    client_id: UUID,
    payload: BaselineGoalRequest,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Set the plan-end monthly lead goal, e.g. to the newest locked baseline's 12-month figure."""
    client = _staff_client(db, user, client_id)
    client_service.update_client(db, client, ClientUpdate(monthly_lead_goal=payload.monthly_lead_goal))
    return baseline_lock.goal_state(db, client)


@router.post("/{client_id}/baseline/lock")
def lock_baseline(
    client_id: UUID,
    payload: BaselineLockRequest,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Freeze a baseline as the next version. Any staff may lock.

    The numbers are recomputed here from the data; nothing the screen shows is
    trusted. Every blocker must be acknowledged, and a re-baseline needs a reason.
    """
    client = _staff_client(db, user, client_id)
    try:
        return baseline_lock.lock(db, client, user.email, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{client_id}/baseline/versions")
def list_baseline_versions(
    client_id: UUID,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    """Every locked baseline for the client, newest first."""
    client = _staff_client(db, user, client_id)
    return baseline_lock.list_versions(db, client)


@router.get("/{client_id}/baseline/versions/{version}")
def get_baseline_version(
    client_id: UUID,
    version: int,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """One locked baseline with the full analysis it was locked from."""
    client = _staff_client(db, user, client_id)
    found = baseline_lock.get_version(db, client, version)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such baseline version")
    return found


@router.post("/{client_id}/baseline/from-ga4", response_model=BaselineSnapshotPreviewOut)
def apply_baseline_from_ga4(
    client_id: UUID,
    payload: BaselineSnapshotApplyRequest,
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> BaselineSnapshotPreviewOut:
    if not user_can_access_client(db, user, client_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this client")
    client = client_service.get_client(db, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    try:
        _, preview = baseline_snapshot.apply_baseline_from_ga4(
            db,
            client,
            monthly_lead_goal=payload.monthly_lead_goal,
            notes=payload.notes,
            as_of=payload.as_of,
            lookback_days=payload.lookback_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return BaselineSnapshotPreviewOut.model_validate(preview)


@router.get("/current/context", response_model=ClientOut)
def current_client_context(
    client: Annotated[Client, Depends(require_client)],
) -> ClientOut:
    return client_out(client)
