"""The consulting portal's API, and the consultant's workspace behind it.

Two kinds of route live here, on purpose apart from every internal router:
- the portal (`require_portal_access`): what a client's own team sees. It returns only what is written for them: no tier, allowance, integration or internal note.
- the workspace (`require_sma_staff`): the consultant's own notes and drafts.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.portal import Portal, portal_clients, require_portal_access
from app.core.security import STAFF_ROLES, AuthUser, get_current_user, require_sma_staff
from app.models.client import Client
from app.models.consulting import ConsultingProfile

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
    return {**{f: getattr(row, f) if row else None for f in FIELDS}, "updated_by": row.updated_by if row else None, "updated_at": row.updated_at.isoformat() if row and row.updated_at else None}


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
    row.updated_by = user.email
    db.commit()
    db.refresh(row)
    return _profile_out(row)
