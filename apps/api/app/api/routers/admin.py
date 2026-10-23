from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.client_scope import list_accessible_client_ids, require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_admin, require_sma_staff
from app.models.client import Client, Tier
from app.models.config import (
    ChannelRule,
    ClientConversionPage,
    ConversionDefinition,
    LeadExclusion,
    Topic,
)
from app.models.integration import Integration
from app.models.job import SyncJob
from app.models.user import User, UserClient, UserRole
from app.services import baseline_reset, engine_input_coverage
from app.services.ga4_event_candidates import load_event_candidates
from app.services.data_health import (
    WATERMARK_SOURCES,
    integration_status_label,
    load_client_data_health,
)
from app.schemas import (
    BaselineResetRequest,
    ClientTeamMemberOut,
    ChannelRuleOut,
    ConversionDefinitionCreate,
    ConversionDefinitionOut,
    ConversionPageIn,
    ConversionPageOut,
    LeadExclusionIn,
    LeadExclusionOut,
    TierCreate,
    TierOut,
    TopicCreate,
    TopicOut,
    UserClientAssign,
    UserClientRemove,
    UserOut,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/tiers", response_model=list[TierOut])
def list_tiers(
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[TierOut]:
    rows = db.query(Tier).order_by(Tier.tier_name.asc()).all()
    return [TierOut.model_validate(r) for r in rows]


@router.post("/tiers", response_model=TierOut, status_code=status.HTTP_201_CREATED)
def create_tier(
    payload: TierCreate,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> TierOut:
    tier = Tier(**payload.model_dump())
    db.add(tier)
    db.commit()
    db.refresh(tier)
    return TierOut.model_validate(tier)


@router.get("/channel-rules", response_model=list[ChannelRuleOut])
def list_channel_rules(
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ChannelRuleOut]:
    rows = db.query(ChannelRule).order_by(ChannelRule.priority.asc()).all()
    return [ChannelRuleOut.model_validate(r) for r in rows]


@router.get("/conversion-definitions", response_model=list[ConversionDefinitionOut])
def list_conversion_definitions(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ConversionDefinitionOut]:
    rows = (
        db.query(ConversionDefinition)
        .filter(ConversionDefinition.client_id == client.id)
        .order_by(ConversionDefinition.conversion_name.asc())
        .all()
    )
    return [ConversionDefinitionOut.model_validate(r) for r in rows]


@router.post(
    "/conversion-definitions",
    response_model=ConversionDefinitionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_conversion_definition(
    payload: ConversionDefinitionCreate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> ConversionDefinitionOut:
    row = ConversionDefinition(client_id=client.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return ConversionDefinitionOut.model_validate(row)


@router.get("/lead-exclusions", response_model=list[LeadExclusionOut])
def list_lead_exclusions(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[LeadExclusionOut]:
    rows = (
        db.query(LeadExclusion)
        .filter(LeadExclusion.client_id == client.id)
        .order_by(LeadExclusion.created_at.asc())
        .all()
    )
    return [LeadExclusionOut.model_validate(r) for r in rows]


@router.put("/lead-exclusions", response_model=list[LeadExclusionOut])
def replace_lead_exclusions(
    payload: list[LeadExclusionIn],
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[LeadExclusionOut]:
    """Replace the whole list of test-lead rules, as the screen edits it.

    A rule needs a reason and at least one thing to match on: one with
    neither would either be unreviewable or drop every lead.
    """
    cleaned: list[dict] = []
    for entry in payload:
        data = {
            "url_pattern": (entry.url_pattern or "").strip() or None,
            "event_name": (entry.event_name or "").strip() or None,
            "session_source": (entry.session_source or "").strip() or None,
            "date_from": entry.date_from,
            "date_to": entry.date_to,
            "reason": entry.reason.strip(),
        }
        if not data["reason"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Every exclusion needs a reason.")
        if not any(data[k] for k in ("url_pattern", "event_name", "session_source", "date_from", "date_to")):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="An exclusion must match on a page, event, source or date, or it would drop every lead.",
            )
        if data["date_from"] and data["date_to"] and data["date_from"] > data["date_to"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="date_from is after date_to.")
        cleaned.append(data)

    db.query(LeadExclusion).filter(LeadExclusion.client_id == client.id).delete(synchronize_session=False)
    for data in cleaned:
        db.add(LeadExclusion(client_id=client.id, **data))
    db.commit()
    return list_lead_exclusions(client=client, _=_, db=db)


@router.get("/conversion-pages", response_model=list[ConversionPageOut])
def list_conversion_pages(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ConversionPageOut]:
    rows = (
        db.query(ClientConversionPage)
        .filter(ClientConversionPage.client_id == client.id)
        .order_by(ClientConversionPage.is_primary.desc(), ClientConversionPage.label.asc())
        .all()
    )
    return [ConversionPageOut.model_validate(r) for r in rows]


@router.put("/conversion-pages", response_model=list[ConversionPageOut])
def replace_conversion_pages(
    payload: list[ConversionPageIn],
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ConversionPageOut]:
    """Replace the whole list, because that is how the screen edits it.

    One primary at most: the engine falls back to the primary offer when a
    page's stage matches nothing, so two of them is a silent coin toss.
    """
    seen: set[str] = set()
    cleaned: list[ConversionPageIn] = []
    for entry in payload:
        url = entry.normalized_url.strip()
        if not url:
            continue
        if url in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{url} is listed twice",
            )
        seen.add(url)
        cleaned.append(entry)

    if sum(1 for e in cleaned if e.is_primary) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only one page can be the primary offer",
        )

    db.query(ClientConversionPage).filter(
        ClientConversionPage.client_id == client.id
    ).delete(synchronize_session=False)
    for entry in cleaned:
        db.add(
            ClientConversionPage(
                client_id=client.id,
                normalized_url=entry.normalized_url.strip(),
                label=entry.label.strip(),
                stage=(entry.stage or None),
                is_primary=entry.is_primary,
            )
        )
    db.commit()
    return list_conversion_pages(client=client, _=_, db=db)


@router.delete(
    "/conversion-definitions/{definition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_conversion_definition(
    definition_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    row = (
        db.query(ConversionDefinition)
        .filter(
            ConversionDefinition.id == definition_id,
            ConversionDefinition.client_id == client.id,
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversion not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversion-definitions/ga4-events")
def list_ga4_events_for_conversions(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    """Every event this client reports, with what is needed to judge it.

    This returned a name and an all-time total, which flatters an event that
    stopped reporting months ago. It carries the 90-day count, how many
    landing pages fired it, whether GA4 collects it on its own, and whether
    the name reads as a lead — see `ga4_event_candidates`.
    """
    return [c.as_dict() for c in load_event_candidates(db, client.id)]


@router.put("/conversion-definitions", response_model=list[ConversionDefinitionOut])
def replace_conversion_definitions(
    payload: list[ConversionDefinitionCreate],
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ConversionDefinitionOut]:
    """Replace the whole set, because that is how the screen edits it.

    The screen is a list of the client's events with a tick against each.
    Adding them one at a time through a typed form is why twenty clients
    have none, and why the Lead branch has never run for them.

    One primary at most, as with conversion pages: the engine falls back to
    the primary conversion, and two of them is a silent coin toss.
    """
    seen: set[str] = set()
    cleaned: list[ConversionDefinitionCreate] = []
    primary_taken = False
    for entry in payload:
        name = entry.event_name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        is_primary = entry.is_primary and not primary_taken
        primary_taken = primary_taken or is_primary
        cleaned.append(
            entry.model_copy(
                update={
                    "event_name": name,
                    "conversion_name": entry.conversion_name.strip() or name,
                    "is_primary": is_primary,
                }
            )
        )

    # Exactly one lead is primary. Without this the first client to tick two
    # gets whichever the database returns first.
    if cleaned and not primary_taken:
        leads = [c for c in cleaned if c.conversion_type == "lead"]
        if leads:
            leads[0].is_primary = True

    db.query(ConversionDefinition).filter(
        ConversionDefinition.client_id == client.id
    ).delete(synchronize_session=False)
    rows = [
        ConversionDefinition(client_id=client.id, **entry.model_dump())
        for entry in cleaned
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return [ConversionDefinitionOut.model_validate(r) for r in rows]


def _visible_clients(db: Session, user: AuthUser):
    """Clients this person is assigned to; every client for an admin.

    The three platform views below used to list everyone's clients to any
    staff account. A newly added team member with no assignments could read
    every client's name, domain, integration status, data-health detail and
    job error text. They follow the same rule as the portfolio: you see what
    you are assigned.
    """
    query = db.query(Client)
    ids = list_accessible_client_ids(db, user)
    if ids is not None:
        query = query.filter(Client.id.in_(ids))
    return query


@router.get("/platform/overview")
def platform_overview(
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    clients = _visible_clients(db, user).order_by(Client.client_name.asc()).all()
    # One query for every client's integrations, not one per client.
    by_client: dict[UUID, dict[str, Integration]] = {}
    if clients:
        for row in db.query(Integration).filter(
            Integration.client_id.in_([c.id for c in clients])
        ):
            by_client.setdefault(row.client_id, {})[row.provider.value] = row
    overview: list[dict] = []
    for client in clients:
        integrations = by_client.get(client.id, {})
        health = load_client_data_health(db, client.id)
        healthy = sum(1 for row in health if row["status"] == "Healthy")
        overview.append(
            {
                "client_id": str(client.id),
                "client_name": client.client_name,
                "client_slug": client.slug,
                "domain": client.domain,
                "status": client.status.value,
                "integrations": {
                    "gsc": integration_status_label(integrations.get("gsc")),
                    "ga4": integration_status_label(integrations.get("ga4")),
                    "se_ranking": integration_status_label(integrations.get("se_ranking")),
                },
                "sources_healthy": healthy,
                "sources_total": len(WATERMARK_SOURCES),
            }
        )
    return overview


@router.get("/platform/data-health")
def platform_data_health(
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    clients = _visible_clients(db, user).order_by(Client.client_name.asc()).all()
    rows: list[dict] = []
    for client in clients:
        for health in load_client_data_health(db, client.id):
            rows.append(
                {
                    "client_id": str(client.id),
                    "client_name": client.client_name,
                    "client_slug": client.slug,
                    **health,
                }
            )
    return rows


@router.get("/platform/jobs")
def platform_jobs(
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 100,
) -> list[dict]:
    capped = max(1, min(limit, 200))
    query = db.query(SyncJob, Client).join(Client, Client.id == SyncJob.client_id)
    ids = list_accessible_client_ids(db, user)
    if ids is not None:
        query = query.filter(SyncJob.client_id.in_(ids))
    jobs = query.order_by(SyncJob.created_at.desc()).limit(capped).all()
    return [
        {
            "id": str(job.id),
            "client_id": str(job.client_id),
            "client_name": client.client_name,
            "client_slug": client.slug,
            "source": job.source,
            "start_date": job.start_date.isoformat(),
            "end_date": job.end_date.isoformat(),
            "status": job.status.value,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }
        for job, client in jobs
    ]


@router.get("/topics", response_model=list[TopicOut])
def list_topics(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[TopicOut]:
    rows = (
        db.query(Topic)
        .filter(Topic.client_id == client.id)
        .order_by(Topic.priority.desc(), Topic.topic_name.asc())
        .all()
    )
    return [TopicOut.model_validate(r) for r in rows]


@router.post("/topics", response_model=TopicOut, status_code=status.HTTP_201_CREATED)
def create_topic(
    payload: TopicCreate,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> TopicOut:
    row = Topic(client_id=client.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return TopicOut.model_validate(row)


@router.post("/user-clients", status_code=status.HTTP_201_CREATED)
def assign_user_client(
    payload: UserClientAssign,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    user = db.query(User).filter(User.id == payload.user_id).one_or_none()
    client = db.query(Client).filter(Client.id == payload.client_id).one_or_none()
    if user is None or client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User or client not found")

    existing = (
        db.query(UserClient)
        .filter(UserClient.user_id == payload.user_id, UserClient.client_id == payload.client_id)
        .one_or_none()
    )
    if existing is None:
        db.add(UserClient(user_id=payload.user_id, client_id=payload.client_id, role=payload.role))
    else:
        existing.role = payload.role
    db.commit()
    return {"ok": True}


@router.get("/data-health")
def data_health(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    return load_client_data_health(db, client.id)


@router.get("/users", response_model=list[UserOut])
def list_users(
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[UserOut]:
    """Staff users, for assigning client access."""
    rows = db.query(User).order_by(User.email.asc()).all()
    return [UserOut.model_validate(row) for row in rows]


@router.get("/clients/{client_id}/team", response_model=list[ClientTeamMemberOut])
def client_team(
    client_id: UUID,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ClientTeamMemberOut]:
    """
    Who can see this client.

    Admins are included because they can see every client without an
    assignment — leaving them out would make the list read as "nobody has
    access" when in fact several people do.
    """
    out: list[ClientTeamMemberOut] = []

    for user in db.query(User).filter(User.role == UserRole.SMA_ADMIN).all():
        out.append(
            ClientTeamMemberOut(
                user_id=user.id,
                email=user.email,
                name=user.name,
                role=user.role,
                is_active=user.is_active,
                via_admin=True,
            )
        )

    assigned = (
        db.query(UserClient, User)
        .join(User, User.id == UserClient.user_id)
        .filter(UserClient.client_id == client_id)
        .all()
    )
    admin_ids = {row.user_id for row in out}
    for link, user in assigned:
        if user.id in admin_ids:
            continue
        out.append(
            ClientTeamMemberOut(
                user_id=user.id,
                email=user.email,
                name=user.name,
                role=link.role,
                is_active=user.is_active,
                via_admin=False,
            )
        )

    return sorted(out, key=lambda row: (not row.via_admin, row.email))


@router.delete("/user-clients", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def unassign_user_client(
    payload: UserClientRemove,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    link = (
        db.query(UserClient)
        .filter(
            UserClient.user_id == payload.user_id,
            UserClient.client_id == payload.client_id,
        )
        .one_or_none()
    )
    if link is not None:
        db.delete(link)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/engine-input-coverage")
def engine_input_coverage_report(
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Per client: which mapped pages the engine can read, and which saved actions rest on one it could not. Changes nothing."""
    return engine_input_coverage.report(db)


@router.get("/baselines/reset-preview")
def baseline_reset_preview(
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Which clients have a baseline or goal that a reset would clear. Changes nothing."""
    return baseline_reset.preview(db)


@router.post("/baselines/reset")
def baseline_reset_run(
    payload: BaselineResetRequest,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Clear baselines and goals (all clients, or those listed) so they can be re-baselined.

    Admin only, irreversible, and it returns everything it removed so a copy can be kept.
    """
    if payload.confirm != baseline_reset.CONFIRMATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Type {baseline_reset.CONFIRMATION} to confirm. Nothing was changed.",
        )
    return baseline_reset.reset(db, payload.client_ids or None)
