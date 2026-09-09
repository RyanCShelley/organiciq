from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.client_scope import list_accessible_client_ids
from app.core.crypto import decrypt_json
from app.core.security import AuthUser
from app.ingestion.google_credentials import (
    upsert_google_credentials_for_client,
    workspace_google_refresh_token,
)
from app.models.client import Client
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.schemas import ClientCreate, ClientUpdate, IntegrationCreate, IntegrationUpdate

# FKs have no ON DELETE CASCADE — delete client-scoped rows before clients.
_CLIENT_CASCADE_TABLES = (
    "staging_ser_ai_checks",
    "staging_ser_ai_prompts",
    "staging_ser_ai_presence",
    "staging_ser_ai_tracker_stats",
    "facts_ser_ai_checks",
    "facts_ser_ai_presence",
    "facts_ser_ai_tracker_stats",
    "facts_ser_ai_prompts",
    "staging_ser_competitors",
    "staging_ser_site_summary",
    "facts_ser_site_summary",
    "staging_ser_positions",
    "staging_ser_keywords",
    "facts_ser_competitors",
    "facts_ser_rankings",
    "facts_ser_keywords",
    "staging_ga4_events",
    "staging_ga4_traffic",
    "facts_ga4_events",
    "facts_ga4_traffic",
    "staging_gsc_query_pages",
    "staging_gsc_pages",
    "staging_gsc_daily",
    "facts_gsc_query_pages",
    "facts_gsc_pages",
    "facts_gsc_daily",
    "facts_crawl_page_snapshots",
    "staging_ser_audit_pages",
    "sync_jobs",
    "data_watermarks",
    "decisions",
    "decision_thresholds",
    "annotations",
    "integrations",
    "conversion_definitions",
    "topics",
    "user_clients",
)


def list_clients(db: Session, user: AuthUser) -> list[Client]:
    query = db.query(Client).order_by(Client.client_name.asc())
    accessible = list_accessible_client_ids(db, user)
    if accessible is not None:
        query = query.filter(Client.id.in_(accessible))
    return query.all()


def get_client(db: Session, client_id: UUID) -> Client | None:
    return db.query(Client).filter(Client.id == client_id).one_or_none()


def create_client(db: Session, payload: ClientCreate) -> Client:
    client = Client(**payload.model_dump())
    db.add(client)
    db.flush()

    for provider in IntegrationProvider:
        db.add(
            Integration(
                client_id=client.id,
                provider=provider,
                connection_status=ConnectionStatus.NOT_CONNECTED,
            )
        )
    db.flush()

    # Copy shared Google Data OAuth onto the new client's GSC/GA4 rows when present.
    shared = workspace_google_refresh_token(db)
    if shared:
        donor = (
            db.query(Integration)
            .filter(
                Integration.provider.in_((IntegrationProvider.GSC, IntegrationProvider.GA4)),
                Integration.credentials.isnot(None),
            )
            .first()
        )
        if donor and donor.credentials:
            try:
                upsert_google_credentials_for_client(
                    db, client.id, decrypt_json(donor.credentials), commit=False
                )
            except Exception:  # noqa: BLE001
                upsert_google_credentials_for_client(
                    db, client.id, {"refresh_token": shared}, commit=False
                )

    db.commit()
    db.refresh(client)
    return client


def update_client(db: Session, client: Client, payload: ClientUpdate) -> Client:
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(client, key, value)
    db.commit()
    db.refresh(client)
    return client


def delete_client(db: Session, client_id: UUID) -> bool:
    client = get_client(db, client_id)
    if client is None:
        return False

    for table in _CLIENT_CASCADE_TABLES:
        db.execute(text(f"DELETE FROM {table} WHERE client_id = :id"), {"id": client_id})
    db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
    db.commit()
    return True


def list_integrations(db: Session, client_id: UUID) -> list[Integration]:
    return (
        db.query(Integration)
        .filter(Integration.client_id == client_id)
        .order_by(Integration.provider.asc())
        .all()
    )


def create_or_update_integration(
    db: Session, client_id: UUID, payload: IntegrationCreate
) -> Integration:
    existing = (
        db.query(Integration)
        .filter(Integration.client_id == client_id, Integration.provider == payload.provider)
        .one_or_none()
    )
    if existing is None:
        integration = Integration(client_id=client_id, **payload.model_dump())
        db.add(integration)
    else:
        for key, value in payload.model_dump().items():
            setattr(existing, key, value)
        integration = existing
    db.commit()
    db.refresh(integration)
    return integration


def update_integration(
    db: Session, client_id: UUID, integration_id: UUID, payload: IntegrationUpdate
) -> Integration | None:
    integration = (
        db.query(Integration)
        .filter(Integration.id == integration_id, Integration.client_id == client_id)
        .one_or_none()
    )
    if integration is None:
        return None
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(integration, key, value)
    db.commit()
    db.refresh(integration)
    return integration
