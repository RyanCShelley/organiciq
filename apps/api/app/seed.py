"""Seed SMA Marketing + admin/team users for local development."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.client import Client, ClientStatus, Tier
from app.models.config import ConversionDefinition
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.models.user import User, UserClient, UserRole

DEFAULT_TIER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")  # Launch
LIFT_TIER_ID = uuid.UUID("11111111-1111-1111-1111-111111111112")
LEAD_TIER_ID = uuid.UUID("11111111-1111-1111-1111-111111111113")
LEGACY_TIER_ID = uuid.UUID("11111111-1111-1111-1111-111111111110")
ENTERPRISE_TIER_ID = uuid.UUID("11111111-1111-1111-1111-111111111114")
SMA_CLIENT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BEACON_CLIENT_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
ADMIN_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
TEAM_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


def _delete_client_cascade(db: Session, client_id: uuid.UUID) -> None:
    """Remove a client and client-scoped rows (FKs have no ON DELETE CASCADE)."""
    tables = [
        "staging_ser_ai_checks",
        "staging_ser_ai_prompts",
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
        "clients",
    ]
    for table in tables:
        if table == "clients":
            db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client_id})
        else:
            db.execute(text(f"DELETE FROM {table} WHERE client_id = :id"), {"id": client_id})


def seed(db: Session) -> None:
    for tier_id, name in (
        (LEGACY_TIER_ID, "Legacy"),
        (DEFAULT_TIER_ID, "Launch"),
        (LIFT_TIER_ID, "Lift"),
        (LEAD_TIER_ID, "Lead"),
        (ENTERPRISE_TIER_ID, "Enterprise"),
    ):
        if db.query(Tier).filter(Tier.id == tier_id).one_or_none() is None:
            raise RuntimeError(f"Tier {name} missing — run alembic upgrade head first")

    for legacy_id in ():
        if db.query(Client).filter(Client.id == legacy_id).one_or_none() is not None:
            _delete_client_cascade(db, legacy_id)

    # Drop stray demo-named clients that are not part of the local multi-client seed set.
    seeded_ids = {SMA_CLIENT_ID, BEACON_CLIENT_ID}
    for row in db.query(Client).filter(Client.client_name.in_(["Acme Manufacturing"])).all():
        if row.id not in seeded_ids:
            _delete_client_cascade(db, row.id)

    def _ensure_client(
        *,
        client_id: uuid.UUID,
        client_name: str,
        domain: str,
        tier_id: uuid.UUID = DEFAULT_TIER_ID,
        monthly_lead_goal: int | None = None,
    ) -> Client:
        client = db.query(Client).filter(Client.id == client_id).one_or_none()
        if client is None:
            client = Client(
                id=client_id,
                client_name=client_name,
                domain=domain,
                tier_id=tier_id,
                start_date=date(2025, 1, 1),
                primary_market="United States",
                timezone="America/New_York",
                monthly_lead_goal=monthly_lead_goal,
                status=ClientStatus.ACTIVE,
            )
            db.add(client)
            db.flush()
        else:
            client.client_name = client_name
            client.domain = domain
            client.tier_id = tier_id
            client.status = ClientStatus.ACTIVE
            if monthly_lead_goal is not None:
                client.monthly_lead_goal = monthly_lead_goal

        for provider in IntegrationProvider:
            exists = (
                db.query(Integration)
                .filter(Integration.client_id == client.id, Integration.provider == provider)
                .one_or_none()
            )
            if exists is None:
                db.add(
                    Integration(
                        client_id=client.id,
                        provider=provider,
                        connection_status=ConnectionStatus.NOT_CONNECTED,
                    )
                )
        return client

    _ensure_client(
        client_id=SMA_CLIENT_ID,
        client_name="SMA Marketing",
        domain="smamarketing.net",
        tier_id=LIFT_TIER_ID,
        monthly_lead_goal=25,
    )
    _ensure_client(
        client_id=BEACON_CLIENT_ID,
        client_name="Beacon Industrial",
        domain="beaconindustrial.com",
        tier_id=DEFAULT_TIER_ID,
        monthly_lead_goal=10,
    )

    if db.query(User).filter(User.id == ADMIN_ID).one_or_none() is None:
        db.add(
            User(
                id=ADMIN_ID,
                email="admin@smamarketing.net",
                name="SMA Admin",
                google_sub="seed-admin",
                role=UserRole.SMA_ADMIN,
            )
        )

    if db.query(User).filter(User.id == TEAM_ID).one_or_none() is None:
        db.add(
            User(
                id=TEAM_ID,
                email="team@smamarketing.net",
                name="SMA Team",
                google_sub="seed-team",
                role=UserRole.SMA_TEAM,
            )
        )
        db.flush()
        db.add(
            UserClient(
                user_id=TEAM_ID,
                client_id=SMA_CLIENT_ID,
                role=UserRole.SMA_TEAM,
            )
        )
    else:
        assignment = (
            db.query(UserClient)
            .filter(UserClient.user_id == TEAM_ID, UserClient.client_id == SMA_CLIENT_ID)
            .one_or_none()
        )
        if assignment is None:
            db.add(
                UserClient(
                    user_id=TEAM_ID,
                    client_id=SMA_CLIENT_ID,
                    role=UserRole.SMA_TEAM,
                )
            )

    lead_def = (
        db.query(ConversionDefinition)
        .filter(
            ConversionDefinition.client_id == SMA_CLIENT_ID,
            ConversionDefinition.event_name == "generate_lead",
        )
        .one_or_none()
    )
    if lead_def is None:
        db.add(
            ConversionDefinition(
                client_id=SMA_CLIENT_ID,
                event_name="generate_lead",
                conversion_name="Lead Form Submission",
                conversion_type="lead",
                is_primary=True,
                active=True,
            )
        )

    db.commit()
    print(
        "Seed complete: SMA Marketing + Beacon Industrial clients, admin@ and team@ users"
    )


if __name__ == "__main__":
    session = SessionLocal()
    try:
        seed(session)
    finally:
        session.close()
