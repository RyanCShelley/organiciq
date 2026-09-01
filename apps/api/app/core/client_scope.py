from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import AuthUser, get_current_user
from app.models.client import Client
from app.models.user import UserClient, UserRole


def require_client(
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    x_organiciq_client_id: Annotated[str | None, Header(alias="X-OrganicIQ-Client-Id")] = None,
) -> Client:
    if not x_organiciq_client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-OrganicIQ-Client-Id header is required",
        )

    try:
        client_id = UUID(x_organiciq_client_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid client id",
        ) from exc

    client = db.query(Client).filter(Client.id == client_id).one_or_none()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    if not user_can_access_client(db, user, client.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized for this client",
        )

    return client


def user_can_access_client(db: Session, user: AuthUser, client_id: UUID) -> bool:
    if user.role == UserRole.SMA_ADMIN:
        return True

    if user.role == UserRole.SMA_TEAM:
        assignment = (
            db.query(UserClient)
            .filter(UserClient.user_id == user.id, UserClient.client_id == client_id)
            .one_or_none()
        )
        return assignment is not None

    if user.role in {UserRole.CLIENT_ADMIN, UserRole.CLIENT_VIEWER}:
        assignment = (
            db.query(UserClient)
            .filter(UserClient.user_id == user.id, UserClient.client_id == client_id)
            .one_or_none()
        )
        return assignment is not None

    return False


def list_accessible_client_ids(db: Session, user: AuthUser) -> list[UUID] | None:
    """Return None for SMA admin (all clients). Otherwise list of accessible client IDs."""
    if user.role == UserRole.SMA_ADMIN:
        return None

    rows = db.query(UserClient.client_id).filter(UserClient.user_id == user.id).all()
    return [row[0] for row in rows]
