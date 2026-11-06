from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.core.client_scope import list_accessible_client_ids
from app.core.crypto import decrypt_json
from app.core.security import AuthUser
from app.ingestion.google_credentials import (
    upsert_google_credentials_for_client,
    workspace_google_refresh_token,
)
from app.models.client import Client, ClientGroup, Tier
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.schemas import ClientCreate, ClientUpdate, IntegrationCreate, IntegrationUpdate
from app.services.competitors import clean_competitor_domains

def slugify_client_name(value: str) -> str:
    text_value = value.strip().lower()
    text_value = re.sub(r"[^a-z0-9]+", "-", text_value)
    text_value = re.sub(r"-{2,}", "-", text_value).strip("-")
    return text_value or "client"


#: Top-level addresses of the web app. A client slug is the first part of a client's address, so one of these would hide that client (or the page).
RESERVED_SLUGS = frozenset({"consulting", "admin", "new-client", "login", "api"})


def allocate_client_slug(
    db: Session,
    *,
    desired: str,
    exclude_client_id: UUID | None = None,
) -> str:
    base = slugify_client_name(desired)
    candidate = base
    n = 2
    while True:
        query = db.query(Client).filter(Client.slug == candidate)
        if exclude_client_id is not None:
            query = query.filter(Client.id != exclude_client_id)
        if candidate not in RESERVED_SLUGS and query.one_or_none() is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1


def list_clients(db: Session, user: AuthUser) -> list[Client]:
    # The tier comes back with the row. Every client is serialised with its
    # resolved plan allowance, which reads `client.tier`, so lazy-loading it
    # cost one query per client on a page that lists all of them.
    query = (
        db.query(Client).options(joinedload(Client.tier)).order_by(Client.client_name.asc())
    )
    accessible = list_accessible_client_ids(db, user)
    if accessible is not None:
        query = query.filter(Client.id.in_(accessible))
    return query.all()


def get_client(db: Session, client_id: UUID) -> Client | None:
    return (
        db.query(Client)
        .options(joinedload(Client.tier))
        .filter(Client.id == client_id)
        .one_or_none()
    )


def clean_brand_aliases(values: list[str] | None) -> list[str]:
    """Lowercase, single-spaced, deduplicated, and long enough to mean something.

    Matched as a phrase inside a query, so a two-letter alias would turn
    every query containing those letters into navigation.
    """
    seen: dict[str, None] = {}
    for value in values or []:
        text = " ".join(str(value).lower().split())
        if len(text) >= 3:
            seen[text] = None
    return list(seen)


CONSULTING_TIER = "Consulting"


def consulting_tier(db: Session) -> Tier:
    """The tier consulting clients sit on: no monthly growth actions, content or updates (the work is done by their own team), room to track the watchlist."""
    tier = db.query(Tier).filter(Tier.tier_name == CONSULTING_TIER).one_or_none()
    if tier is None:
        tier = Tier(tier_name=CONSULTING_TIER, tracked_keyword_limit=100, tracked_prompt_limit=25, content_allowance=0, update_allowance=0, growth_action_allowance=0, conversion_limit=10, reporting_level="standard")
        db.add(tier)
        db.flush()
    return tier


def group_for(db: Session, name: str | None) -> ClientGroup | None:
    """The group with this name (case aside), made when it is new. A blank name is no group."""
    clean = " ".join((name or "").split())
    if not clean:
        return None
    for g in db.query(ClientGroup).all():
        if g.name.lower() == clean.lower():
            return g
    slug_base = "".join(c if c.isalnum() else "-" for c in clean.lower()).strip("-") or "group"
    slug, n = slug_base, 2
    while db.query(ClientGroup).filter(ClientGroup.slug == slug).first():
        slug, n = f"{slug_base}-{n}", n + 1
    group = ClientGroup(name=clean, slug=slug)
    db.add(group)
    db.flush()
    return group


def create_client(db: Session, payload: ClientCreate) -> Client:
    data = payload.model_dump()
    group = group_for(db, data.pop("group_name", None))
    data["group_id"] = group.id if group else None
    if data.get("tier_id") is None:
        data["tier_id"] = consulting_tier(db).id
    # Resolved from the tier when a client is read; there is no column for them.
    data.pop("growth_action_allowance", None)
    data.pop("plan_label", None)
    data["brand_aliases"] = clean_brand_aliases(data.get("brand_aliases"))
    data["competitor_domains"] = clean_competitor_domains(
        data.get("competitor_domains"), own_domain=data.get("domain")
    )
    desired_slug = data.pop("slug", None) or data["client_name"]
    data["slug"] = allocate_client_slug(db, desired=desired_slug)
    # New clients pull Search Console lean (see Client.gsc_lean_pull); existing ones keep the full pull until switched.
    data["gsc_lean_pull"] = True
    client = Client(**data)
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


def _clean_lead_goal_overrides(raw: object) -> dict[str, int]:
    """Keep only positive whole goals keyed by checkpoint month.

    These are read on every dashboard load, so junk here would be read back
    forever. Dropping a bad entry rather than rejecting the whole request means
    one mistyped box does not lose the other corrections in the same save.
    """
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, int] = {}
    for key, value in raw.items():
        try:
            month = int(key)
            goal = int(value)
        except (TypeError, ValueError):
            continue
        if month >= 0 and goal > 0:
            cleaned[str(month)] = goal
    return cleaned


def update_client(db: Session, client: Client, payload: ClientUpdate) -> Client:
    data = payload.model_dump(exclude_unset=True)
    if "lead_goal_overrides" in data:
        data["lead_goal_overrides"] = _clean_lead_goal_overrides(data["lead_goal_overrides"])
    if "brand_aliases" in data:
        data["brand_aliases"] = clean_brand_aliases(data["brand_aliases"])
    if "competitor_domains" in data:
        data["competitor_domains"] = clean_competitor_domains(
            data["competitor_domains"], own_domain=data.get("domain") or client.domain
        )
    if "slug" in data and data["slug"]:
        data["slug"] = allocate_client_slug(
            db, desired=str(data["slug"]), exclude_client_id=client.id
        )
    if "group_name" in data:
        group = group_for(db, data.pop("group_name"))
        data["group_id"] = group.id if group else None
    if data.get("service_mode") is None:
        data.pop("service_mode", None)
    for key, value in data.items():
        setattr(client, key, value)
    db.commit()
    db.refresh(client)
    return client


def delete_client(db: Session, client_id: UUID) -> bool:
    client = get_client(db, client_id)
    if client is None:
        return False

    from app import reset_client_data

    reset_client_data.purge(db, client)
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
