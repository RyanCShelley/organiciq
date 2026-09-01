from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.urls import normalize_url
from app.models.gsc import (
    FactGscDaily,
    FactGscPage,
    FactGscQueryPage,
    StagingGscDaily,
    StagingGscPage,
    StagingGscQueryPage,
)
from app.models.job import SyncJob

# psycopg limit is 65535 bind params; keep batches well under that.
UPSERT_BATCH_SIZE = 1000


def _chunked(items: Sequence[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _as_decimal(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _merge_gsc_metrics(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    old_impressions = _as_decimal(existing["impressions"])
    new_impressions = _as_decimal(incoming["impressions"])
    old_clicks = _as_decimal(existing["clicks"])
    new_clicks = _as_decimal(incoming["clicks"])
    old_position = _as_decimal(existing["average_position"])
    new_position = _as_decimal(incoming["average_position"])

    total_impressions = old_impressions + new_impressions
    total_clicks = old_clicks + new_clicks
    if total_impressions > 0:
        weighted_position = (
            old_position * old_impressions + new_position * new_impressions
        ) / total_impressions
        ctr = total_clicks / total_impressions
    else:
        weighted_position = Decimal(0)
        ctr = Decimal(0)

    existing["impressions"] = total_impressions
    existing["clicks"] = total_clicks
    existing["ctr"] = ctr
    existing["average_position"] = weighted_position


def _page_grain_key(payload: dict[str, Any]) -> tuple[Any, ...]:
    return (
        payload["client_id"],
        payload["date"],
        payload["normalized_url"],
        payload["country"],
        payload["device"],
    )


def _query_grain_key(payload: dict[str, Any]) -> tuple[Any, ...]:
    return (
        payload["client_id"],
        payload["date"],
        payload["query"],
        payload["normalized_url"],
        payload["country"],
        payload["device"],
    )


def _dedupe_payloads(
    payloads: list[dict[str, Any]],
    grain_key,
) -> list[dict[str, Any]]:
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    for payload in payloads:
        key = grain_key(payload)
        existing = merged.get(key)
        if existing is None:
            merged[key] = payload
            continue
        _merge_gsc_metrics(existing, payload)
    return list(merged.values())


def publish_gsc_daily(db: Session, job: SyncJob) -> int:
    rows = (
        db.query(StagingGscDaily)
        .filter(StagingGscDaily.job_id == job.id, StagingGscDaily.client_id == job.client_id)
        .all()
    )
    if not rows:
        return 0

    payloads: list[dict[str, Any]] = []
    for row in rows:
        if row.date is None:
            continue
        payloads.append(
            {
                "client_id": job.client_id,
                "date": row.date,
                "impressions": row.impressions or Decimal(0),
                "clicks": row.clicks or Decimal(0),
                "ctr": row.ctr or Decimal(0),
                "average_position": row.average_position or Decimal(0),
            }
        )

    if not payloads:
        return 0

    for batch in _chunked(payloads, UPSERT_BATCH_SIZE):
        stmt = insert(FactGscDaily).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_facts_gsc_daily_grain",
            set_={
                "impressions": stmt.excluded.impressions,
                "clicks": stmt.excluded.clicks,
                "ctr": stmt.excluded.ctr,
                "average_position": stmt.excluded.average_position,
            },
        )
        db.execute(stmt)
    db.commit()
    return len(payloads)


def publish_gsc_pages(db: Session, job: SyncJob) -> int:
    rows = (
        db.query(StagingGscPage)
        .filter(StagingGscPage.job_id == job.id, StagingGscPage.client_id == job.client_id)
        .all()
    )
    if not rows:
        return 0

    payloads: list[dict[str, Any]] = []
    for row in rows:
        if row.date is None or not row.page:
            continue
        payloads.append(
            {
                "client_id": job.client_id,
                "date": row.date,
                "raw_url": row.page,
                "normalized_url": normalize_url(row.page),
                "country": row.country or "",
                "device": row.device or "",
                "impressions": row.impressions or Decimal(0),
                "clicks": row.clicks or Decimal(0),
                "ctr": row.ctr or Decimal(0),
                "average_position": row.average_position or Decimal(0),
            }
        )

    if not payloads:
        return 0

    payloads = _dedupe_payloads(payloads, _page_grain_key)

    for batch in _chunked(payloads, UPSERT_BATCH_SIZE):
        stmt = insert(FactGscPage).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_facts_gsc_pages_grain",
            set_={
                "raw_url": stmt.excluded.raw_url,
                "impressions": stmt.excluded.impressions,
                "clicks": stmt.excluded.clicks,
                "ctr": stmt.excluded.ctr,
                "average_position": stmt.excluded.average_position,
            },
        )
        db.execute(stmt)
    db.commit()
    return len(payloads)


def publish_gsc_queries(db: Session, job: SyncJob) -> int:
    rows = (
        db.query(StagingGscQueryPage)
        .filter(
            StagingGscQueryPage.job_id == job.id,
            StagingGscQueryPage.client_id == job.client_id,
        )
        .all()
    )
    if not rows:
        return 0

    payloads: list[dict[str, Any]] = []
    for row in rows:
        query = (row.query or "").strip()
        if row.date is None or not query or not row.page:
            continue
        payloads.append(
            {
                "client_id": job.client_id,
                "date": row.date,
                "query": query,
                "raw_url": row.page,
                "normalized_url": normalize_url(row.page),
                "country": row.country or "",
                "device": row.device or "",
                "impressions": row.impressions or Decimal(0),
                "clicks": row.clicks or Decimal(0),
                "ctr": row.ctr or Decimal(0),
                "average_position": row.average_position or Decimal(0),
            }
        )

    if not payloads:
        return 0

    payloads = _dedupe_payloads(payloads, _query_grain_key)

    for batch in _chunked(payloads, UPSERT_BATCH_SIZE):
        stmt = insert(FactGscQueryPage).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_facts_gsc_query_pages_grain",
            set_={
                "raw_url": stmt.excluded.raw_url,
                "impressions": stmt.excluded.impressions,
                "clicks": stmt.excluded.clicks,
                "ctr": stmt.excluded.ctr,
                "average_position": stmt.excluded.average_position,
            },
        )
        db.execute(stmt)
    db.commit()
    return len(payloads)


def count_blank_query_facts(db: Session, client_id: UUID) -> int:
    return (
        db.query(FactGscQueryPage)
        .filter(FactGscQueryPage.client_id == client_id, FactGscQueryPage.query == "")
        .count()
    )
