"""Admin for v2: every client at a glance, and removing one for good.

Adding a client is `POST /clients` (admin only), which the Add client screen already uses. Removing one is here, behind
the client's exact name, with a preview of what goes first. Only an SMA admin can do either.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import reset_client_data
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_admin
from app.core.settings import get_settings
from app.models.baseline import BaselineVersion
from app.models.client import Client
from app.models.client_bing_site import ClientBingSite
from app.models.ga4 import FactGa4Traffic
from app.models.gsc import FactGscDaily
from app.models.integration import Integration
from app.models.user import User, UserClient, UserRole
from app.services import data_pull, welcome_email
from app.models.watchlist import WatchlistKeyword

logger = logging.getLogger("organiciq.admin")
router = APIRouter(prefix="/v2/admin", tags=["v2 admin"])


class TeamBulkIn(BaseModel):
    user_ids: list[UUID] = Field(min_length=1, max_length=200)
    client_ids: list[UUID] = Field(min_length=1, max_length=500)


@router.get("/team-access")
def team_access(
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Everyone who can sign in and the clients each can see, for assigning people to clients in bulk.

    An admin sees every client without an assignment, so an admin's list is marked rather than filled in.
    """
    links: dict[UUID, list[str]] = {}
    for user_id, client_id in db.query(UserClient.user_id, UserClient.client_id):
        links.setdefault(user_id, []).append(str(client_id))
    users = [
        {"id": str(u.id), "email": u.email, "name": u.name, "role": u.role.value, "is_active": u.is_active, "sees_all": u.role == UserRole.SMA_ADMIN, "client_ids": links.get(u.id, [])}
        for u in db.query(User).filter(User.role.in_((UserRole.SMA_ADMIN, UserRole.SMA_TEAM, UserRole.SEO_LEAD, UserRole.CONTENT_MANAGER))).order_by(User.email)
    ]
    clients = [{"id": str(c.id), "name": c.client_name, "slug": c.slug, "domain": c.domain, "status": c.status.value if hasattr(c.status, "value") else c.status} for c in db.query(Client).order_by(Client.client_name)]
    return {"users": users, "clients": clients}


def _bulk_targets(db: Session, payload: TeamBulkIn) -> tuple[list[User], list[Client]]:
    user_ids, client_ids = set(payload.user_ids), set(payload.client_ids)
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    clients = db.query(Client).filter(Client.id.in_(client_ids)).all()
    if len(users) != len(user_ids) or len(clients) != len(client_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One of those people or clients no longer exists. Reload the page.")
    return users, clients


@router.post("/team-access/assign")
def team_assign(
    payload: TeamBulkIn,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Give each person access to each client. People who already have it are left as they are, and admins need nothing (they see every client)."""
    users, clients = _bulk_targets(db, payload)
    held = {(u, c) for u, c in db.query(UserClient.user_id, UserClient.client_id).filter(UserClient.user_id.in_([u.id for u in users]), UserClient.client_id.in_([c.id for c in clients]))}
    added = already = 0
    admins = [u for u in users if u.role == UserRole.SMA_ADMIN]
    for user in users:
        if user.role == UserRole.SMA_ADMIN:
            continue
        for client in clients:
            if (user.id, client.id) in held:
                already += 1
            else:
                db.add(UserClient(user_id=user.id, client_id=client.id, role=UserRole.SMA_TEAM))
                added += 1
    db.commit()
    return {"added": added, "already": already, "admins_skipped": len(admins)}


@router.post("/team-access/remove")
def team_remove(
    payload: TeamBulkIn,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Take each person's access to each client away. An admin's access is by role, so it is not removed here."""
    users, clients = _bulk_targets(db, payload)
    removable = [u.id for u in users if u.role != UserRole.SMA_ADMIN]
    removed = db.query(UserClient).filter(UserClient.user_id.in_(removable), UserClient.client_id.in_([c.id for c in clients])).delete(synchronize_session=False) if removable else 0
    db.commit()
    return {"removed": removed, "admins_skipped": len(users) - len(removable)}


class PersonIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    role: Literal["sma_team", "sma_admin"] = "sma_team"


@router.post("/team-access/people")
def add_person(
    payload: PersonIn,
    admin: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Add someone before they have signed in, so they can be given clients now. They sign in with their own Google account and are matched on the address.

    Only a workspace address is accepted (the same rule sign-in applies). Someone already here is not changed; someone who was removed is let back in.
    """
    email = payload.email.strip().lower()
    if "@" not in email or not get_settings().is_workspace_email(email):
        domains = ", ".join(sorted(get_settings().hosted_domains))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Use a work address ({domains}): that is what they sign in with.")
    user = db.query(User).filter(User.email == email).one_or_none()
    outcome = "added"
    if user is None:
        user = User(email=email, name=(payload.name or "").strip() or None, role=UserRole(payload.role), is_active=True)
        db.add(user)
    elif user.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{email} is already on the team.")
    else:
        user.is_active = True
        outcome = "restored"
    db.commit()
    db.refresh(user)
    emailed = welcome_email.send(name=user.name, email=user.email, added_by=admin.name or admin.email, restored=outcome == "restored")
    return {"outcome": outcome, "id": str(user.id), "email": user.email, "name": user.name, "role": user.role.value, "emailed": emailed}


class PeopleIn(BaseModel):
    user_ids: list[UUID] = Field(min_length=1, max_length=200)


@router.post("/team-access/people/remove")
def remove_people(
    payload: PeopleIn,
    admin: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Take people out of the tool: they can no longer sign in and lose every client assignment. Their account is kept (inactive), so work they
    did stays attributed and Restore brings them back. Not yourself, and not the last active admin."""
    ids = set(payload.user_ids)
    users = db.query(User).filter(User.id.in_(ids)).all()
    if len(users) != len(ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One of those people no longer exists. Reload the page.")
    if admin.id in ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You can't remove yourself. Ask another admin.")
    staying = db.query(User).filter(User.role == UserRole.SMA_ADMIN, User.is_active.is_(True), User.id.notin_(ids)).count()
    if staying == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That would leave no active admin. Keep at least one.")
    removed = 0
    for user in users:
        if user.is_active:
            user.is_active = False
            removed += 1
    db.query(UserClient).filter(UserClient.user_id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"removed": removed}


@router.post("/team-access/people/restore")
def restore_people(
    payload: PeopleIn,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Let people sign in again. Their client assignments are not brought back: give those again."""
    users = db.query(User).filter(User.id.in_(set(payload.user_ids))).all()
    restored = 0
    for user in users:
        if not user.is_active:
            user.is_active = True
            restored += 1
    db.commit()
    return {"restored": restored}


class DeleteIn(BaseModel):
    confirm_name: str


@router.get("/clients")
def admin_clients(
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    """Every client with what is set up and how current its data is, in a handful of grouped queries."""
    def counts(model) -> dict:
        return {cid: n for cid, n in db.query(model.client_id, func.count()).group_by(model.client_id)}

    def newest(model) -> dict:
        return {cid: d for cid, d in db.query(model.client_id, func.max(model.date)).group_by(model.client_id)}

    integrations = counts(Integration)
    watchlist = counts(WatchlistKeyword)
    baselines = counts(BaselineVersion)
    team = counts(UserClient)
    bing = counts(ClientBingSite)
    gsc, ga4 = newest(FactGscDaily), newest(FactGa4Traffic)

    out = []
    for c in db.query(Client).order_by(Client.client_name):
        out.append(
            {
                "id": str(c.id),
                "name": c.client_name,
                "slug": c.slug,
                "domain": c.domain,
                "tier": c.tier.tier_name if c.tier else None,
                "status": c.status.value if c.status else None,
                "business_model": c.business_model,
                "integrations": integrations.get(c.id, 0),
                "bing": bing.get(c.id, 0) > 0,
                "watchlist_keywords": watchlist.get(c.id, 0),
                "has_baseline": baselines.get(c.id, 0) > 0,
                "gsc_lean": bool(c.gsc_lean_pull),
                "team": team.get(c.id, 0),
                "gsc_through": gsc[c.id].isoformat() if gsc.get(c.id) else None,
                "ga4_through": ga4[c.id].isoformat() if ga4.get(c.id) else None,
            }
        )
    return out


def _client(db: Session, client_id: UUID) -> Client:
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


@router.get("/clients/{client_id}/delete-preview")
def delete_preview(
    client_id: UUID,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """What deleting this client removes, by kind, before anyone confirms it."""
    client = _client(db, client_id)
    p = reset_client_data.plan(db, client)
    kept = p["kept"]
    return {
        "name": client.client_name,
        "synced_rows": sum(p["clear_synced"].values()),
        "setup_rows": sum(p["clear_setup"].values()),
        "setup": {t: n for t, n in p["clear_setup"].items() if n},
        "integrations": kept["integrations"],
        "team_access": kept["user_clients"],
        "annotations": kept["annotations"],
        "copilot_conversations": kept["copilot_conversations"],
    }


@router.delete("/clients/{client_id}")
def delete_client(
    client_id: UUID,
    payload: DeleteIn,
    user: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Delete a client and all of its data for good. The exact client name must be sent back."""
    client = _client(db, client_id)
    if payload.confirm_name != client.client_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Type the client's exact name to delete it.")
    name = client.client_name
    deleted = reset_client_data.purge(db, client)
    db.commit()
    logger.warning("Client deleted: %s (%s) by %s, %d rows in %d tables", name, client_id, user.email, sum(deleted.values()), len(deleted))
    return {"deleted": name, "rows": sum(deleted.values()), "tables": len(deleted)}


@router.get("/clients/{client_id}/pull")
def pull_status(
    client_id: UUID,
    _: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """What a pull fetches and how far back, plus where the current pull stands and the time left."""
    return data_pull.pull_status(db, _client(db, client_id))


@router.post("/clients/{client_id}/pull")
def start_pull(
    client_id: UUID,
    user: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
    force: bool = False,
) -> dict:
    """Queue a pull of what is missing: sources never pulled, failed, or older than a day. force pulls everything."""
    client = _client(db, client_id)
    if not data_pull.pull_plan(db, client):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing is connected yet. Connect a data source in Settings first.")
    queued = data_pull.queue_pull(db, client, force=force)
    logger.info("Pull started for %s by %s%s: %s", client.client_name, user.email, " (forced)" if force else "", ", ".join(queued) or "nothing missing")
    return {"queued": queued, **data_pull.pull_status(db, client)}


@router.post("/clients/{client_id}/pull/stop")
def stop_pull(
    client_id: UUID,
    user: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Stop the pull: cancel what is waiting and ask what is running to stop at its next page."""
    client = _client(db, client_id)
    result = data_pull.stop_pull(db, client, user.email)
    logger.warning("Pull stopped for %s by %s: %s", client.client_name, user.email, result)
    return {**result, **data_pull.pull_status(db, client)}


class LeanIn(BaseModel):
    enabled: bool


@router.post("/clients/gsc-lean-all")
def set_gsc_lean_all(
    user: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Switch every client that is still on the full Search Console pull to lean. Each one queues one pull that replaces its old rows."""
    switched = 0
    for client in db.query(Client).filter(Client.gsc_lean_pull.is_(False)).order_by(Client.client_name).all():
        data_pull.set_lean_pull(db, client, True)
        switched += 1
    logger.warning("Search Console pull set to lean for %s clients by %s", switched, user.email)
    return {"switched": switched}


@router.post("/clients/{client_id}/gsc-lean")
def set_gsc_lean(
    client_id: UUID,
    payload: LeanIn,
    user: Annotated[AuthUser, Depends(require_sma_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Switch this client's Search Console pull between lean and full. It clears the client's pages and searches and pulls them again."""
    client = _client(db, client_id)
    queued = data_pull.set_lean_pull(db, client, payload.enabled)
    logger.warning("Search Console pull set to %s for %s by %s; queued %s", "lean" if payload.enabled else "full", client.client_name, user.email, queued)
    return {"gsc_lean": bool(client.gsc_lean_pull), "queued": queued}


#: Where the address is read from: a service that answers with the address the request came from.
OUTBOUND_IP_SERVICE = "https://api.ipify.org"


@router.get("/outbound-ip")
def outbound_ip(_: Annotated[AuthUser, Depends(require_sma_admin)]) -> dict:
    """The address this service is sending from right now, to check against what a host has been told to allow."""
    import httpx

    try:
        found = httpx.get(OUTBOUND_IP_SERVICE, timeout=8.0).text.strip()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"The address could not be looked up: {type(exc).__name__}.") from exc
    return {"address": found, "asked": OUTBOUND_IP_SERVICE, "user_agent": "OrganicIQ-page-diagnostic/1.0"}
