from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_admin, require_sma_staff
from app.models.client import Client, Tier
from app.models.config import ChannelRule, ConversionDefinition, Topic
from app.models.ga4 import FactGa4Event
from app.models.integration import Integration
from app.models.job import SyncJob
from app.models.user import User, UserClient
from app.services.data_health import (
    WATERMARK_SOURCES,
    integration_status_label,
    load_client_data_health,
)
from app.schemas import (
    ChannelRuleOut,
    ConversionDefinitionCreate,
    ConversionDefinitionOut,
    TierCreate,
    TierOut,
    TopicCreate,
    TopicOut,
    UserClientAssign,
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


@router.get("/conversion-definitions/ga4-events")
def list_ga4_events_for_conversions(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    rows = (
        db.query(
            FactGa4Event.event_name,
            func.coalesce(func.sum(FactGa4Event.event_count), 0).label("event_count"),
        )
        .filter(FactGa4Event.client_id == client.id)
        .group_by(FactGa4Event.event_name)
        .order_by(func.sum(FactGa4Event.event_count).desc(), FactGa4Event.event_name.asc())
        .limit(200)
        .all()
    )
    return [{"event_name": name, "event_count": int(count)} for name, count in rows]


@router.get("/platform/overview")
def platform_overview(
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    clients = db.query(Client).order_by(Client.client_name.asc()).all()
    overview: list[dict] = []
    for client in clients:
        integrations = {
            i.provider.value: i
            for i in db.query(Integration).filter(Integration.client_id == client.id).all()
        }
        health = load_client_data_health(db, client.id)
        healthy = sum(1 for row in health if row["status"] == "Healthy")
        overview.append(
            {
                "client_id": str(client.id),
                "client_name": client.client_name,
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
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    clients = db.query(Client).order_by(Client.client_name.asc()).all()
    rows: list[dict] = []
    for client in clients:
        for health in load_client_data_health(db, client.id):
            rows.append(
                {
                    "client_id": str(client.id),
                    "client_name": client.client_name,
                    **health,
                }
            )
    return rows


@router.get("/platform/jobs")
def platform_jobs(
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 100,
) -> list[dict]:
    capped = max(1, min(limit, 200))
    jobs = (
        db.query(SyncJob, Client)
        .join(Client, Client.id == SyncJob.client_id)
        .order_by(SyncJob.created_at.desc())
        .limit(capped)
        .all()
    )
    return [
        {
            "id": str(job.id),
            "client_id": str(job.client_id),
            "client_name": client.client_name,
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
