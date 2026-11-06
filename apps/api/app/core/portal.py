"""Who may open the consulting portal for which client.

The portal is a separate surface from the internal app. Today it is opened by SMA staff (the consultant presenting a client's view). It is written so a
client user can be admitted later without changing any endpoint: a client-role person assigned to one site of a company may open every consulting site in
that company's group, and nobody else's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.client_scope import list_accessible_client_ids, user_can_access_client
from app.core.db import get_db
from app.core.security import STAFF_ROLES, AuthUser, get_current_user
from app.models.client import Client
from app.models.user import UserClient, UserRole

CLIENT_ROLES = frozenset({UserRole.CLIENT_ADMIN, UserRole.CLIENT_VIEWER})


@dataclass(frozen=True)
class Portal:
    client: Client
    user: AuthUser
    is_staff: bool


def portal_clients(db: Session, user: AuthUser) -> list[Client]:
    """The consulting clients this person may open, by name."""
    base = db.query(Client).filter(Client.service_mode == "consulting")
    if user.role in STAFF_ROLES:
        ids = list_accessible_client_ids(db, user)
        rows = base.all() if ids is None else base.filter(Client.id.in_(ids)).all()
    elif user.role in CLIENT_ROLES:
        mine = [c for (c,) in db.query(UserClient.client_id).filter(UserClient.user_id == user.id)]
        groups = [g for (g,) in db.query(Client.group_id).filter(Client.id.in_(mine), Client.group_id.isnot(None))]
        rows = base.filter((Client.id.in_(mine)) | (Client.group_id.in_(groups))).all() if mine else []
    else:
        rows = []
    return sorted(rows, key=lambda c: c.client_name.lower())


def require_portal_access(
    user: Annotated[AuthUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    x_organiciq_client_id: Annotated[str | None, Header(alias="X-OrganicIQ-Client-Id")] = None,
) -> Portal:
    """The client being opened and who is opening it. Refuses anyone not entitled to this client's portal, and any client without one."""
    if not x_organiciq_client_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-OrganicIQ-Client-Id header is required")
    try:
        client_id = UUID(x_organiciq_client_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid client id") from exc
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    if user.role in STAFF_ROLES:
        allowed = user_can_access_client(db, user, client.id)
    elif user.role in CLIENT_ROLES:
        allowed = client.id in {c.id for c in portal_clients(db, user)}
    else:
        allowed = False
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this client")
    if client.service_mode != "consulting":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This client has no consulting portal")
    return Portal(client=client, user=user, is_staff=user.role in STAFF_ROLES)
