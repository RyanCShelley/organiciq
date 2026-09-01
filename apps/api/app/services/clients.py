from uuid import UUID

from sqlalchemy.orm import Session

from app.core.client_scope import list_accessible_client_ids
from app.core.security import AuthUser
from app.models.client import Client
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.schemas import ClientCreate, ClientUpdate, IntegrationCreate, IntegrationUpdate


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
