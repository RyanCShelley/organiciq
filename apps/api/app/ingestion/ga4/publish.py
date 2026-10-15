from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.urls import normalize_landing_page, normalize_path_prefix, url_in_scope
from app.ingestion.channels import classify_channel
from app.models.client import Client
from app.models.config import ChannelRule
from app.models.ga4 import FactGa4Event, FactGa4Traffic, StagingGa4Event, StagingGa4Traffic
from app.models.job import SyncJob

UPSERT_BATCH_SIZE = 1000


def _chunked(items: Sequence[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


TRAFFIC_GRAIN = ("client_id", "date", "normalized_url", "channel", "session_source", "session_medium")
EVENT_GRAIN = TRAFFIC_GRAIN + ("event_name",)


def _merge_on_grain(
    payloads: list[dict[str, Any]], grain: tuple[str, ...], additive: tuple[str, ...]
) -> list[dict[str, Any]]:
    """
    Collapse rows that land on the same fact row, adding their measures.

    GA4 reports a landing page with and without a query string as different
    rows; normalizing the URL makes them one. Sent to Postgres as one upsert
    that is "ON CONFLICT DO UPDATE command cannot affect row a second time",
    which failed triple-m-outfitters' GA4 sync every day since the first such
    pair appeared, with the cause hidden behind a generic worker error.
    """
    merged: dict[tuple, dict[str, Any]] = {}
    for payload in payloads:
        key = tuple(payload[column] for column in grain)
        kept = merged.get(key)
        if kept is None:
            merged[key] = dict(payload)
            continue
        for column in additive:
            if payload[column] is None:
                continue
            kept[column] = payload[column] if kept[column] is None else kept[column] + payload[column]
    return list(merged.values())


def _rules(db: Session) -> list[ChannelRule]:
    return db.query(ChannelRule).filter(ChannelRule.active.is_(True)).order_by(ChannelRule.priority.asc()).all()


def publish_ga4(db: Session, job: SyncJob) -> tuple[int, int]:
    rules = _rules(db)
    client = db.query(Client).filter(Client.id == job.client_id).one()
    domain = client.domain
    # A client scoped to a folder shares its GA4 property with the parent
    # brand, so rows outside that folder are someone else's traffic.
    scope = normalize_path_prefix(client.path_prefix)
    traffic = (
        db.query(StagingGa4Traffic)
        .filter(StagingGa4Traffic.job_id == job.id, StagingGa4Traffic.client_id == job.client_id)
        .all()
    )
    events = (
        db.query(StagingGa4Event)
        .filter(StagingGa4Event.job_id == job.id, StagingGa4Event.client_id == job.client_id)
        .all()
    )

    traffic_payloads: list[dict[str, Any]] = []
    for row in traffic:
        if row.date is None:
            continue
        raw_url = row.landing_page or ""
        normalized = normalize_landing_page(raw_url, domain)
        if not url_in_scope(normalized, scope):
            continue
        traffic_payloads.append(
            {
                "client_id": job.client_id,
                "date": row.date,
                "raw_url": raw_url,
                "normalized_url": normalized,
                "session_source": row.session_source or "",
                "session_medium": row.session_medium or "",
                "channel": classify_channel(row.session_source, row.session_medium, rules),
                "sessions": row.sessions or Decimal(0),
                "active_users": row.active_users or Decimal(0),
                "views": row.views or Decimal(0),
                "engaged_sessions": row.engaged_sessions,
            }
        )

    event_payloads: list[dict[str, Any]] = []
    for row in events:
        if row.date is None or not row.event_name:
            continue
        raw_url = row.landing_page or ""
        normalized = normalize_landing_page(raw_url, domain)
        if not url_in_scope(normalized, scope):
            continue
        event_payloads.append(
            {
                "client_id": job.client_id,
                "date": row.date,
                "raw_url": raw_url,
                "normalized_url": normalized,
                "session_source": row.session_source or "",
                "session_medium": row.session_medium or "",
                "channel": classify_channel(row.session_source, row.session_medium, rules),
                "event_name": row.event_name,
                "event_count": row.event_count or 0,
            }
        )

    traffic_payloads = _merge_on_grain(
        traffic_payloads, TRAFFIC_GRAIN, ("sessions", "active_users", "views", "engaged_sessions")
    )
    event_payloads = _merge_on_grain(event_payloads, EVENT_GRAIN, ("event_count",))

    for batch in _chunked(traffic_payloads, UPSERT_BATCH_SIZE):
        if not batch:
            continue
        stmt = insert(FactGa4Traffic).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_facts_ga4_traffic_grain",
            set_={
                "raw_url": stmt.excluded.raw_url,
                "sessions": stmt.excluded.sessions,
                "active_users": stmt.excluded.active_users,
                "views": stmt.excluded.views,
                "engaged_sessions": stmt.excluded.engaged_sessions,
            },
        )
        db.execute(stmt)

    for batch in _chunked(event_payloads, UPSERT_BATCH_SIZE):
        if not batch:
            continue
        stmt = insert(FactGa4Event).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_facts_ga4_events_grain",
            set_={
                "raw_url": stmt.excluded.raw_url,
                "event_count": stmt.excluded.event_count,
            },
        )
        db.execute(stmt)

    db.commit()
    return len(traffic_payloads), len(event_payloads)
