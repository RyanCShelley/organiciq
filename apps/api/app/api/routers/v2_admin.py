"""Admin for v2: every client at a glance, and removing one for good.

Adding a client is `POST /clients` (admin only), which the Add client screen already uses. Removing one is here, behind
the client's exact name, with a preview of what goes first. Only an SMA admin can do either.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import reset_client_data
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_admin
from app.models.baseline import BaselineVersion
from app.models.client import Client
from app.models.client_bing_site import ClientBingSite
from app.models.ga4 import FactGa4Traffic
from app.models.gsc import FactGscDaily
from app.models.integration import Integration
from app.models.user import UserClient
from app.services import data_pull
from app.models.watchlist import WatchlistKeyword

logger = logging.getLogger("organiciq.admin")
router = APIRouter(prefix="/v2/admin", tags=["v2 admin"])


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
