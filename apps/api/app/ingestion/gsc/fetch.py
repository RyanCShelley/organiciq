from __future__ import annotations

from collections.abc import Iterator

import calendar
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.ingestion.google_credentials import access_token_for_client, client_has_google_credentials
from app.ingestion.gsc.client import query_search_analytics
from app.models.client import Client
from app.models.gsc import StagingGscDaily, StagingGscPage, StagingGscQueryPage
from app.models.integration import Integration, IntegrationProvider
from app.models.job import SyncJob


def _normalize_secondary_urls(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            url = item.strip()
            if url not in out:
                out.append(url)
    return out


def _load_gsc_integration(db: Session, client_id: UUID) -> Integration:
    integration = (
        db.query(Integration)
        .filter(
            Integration.client_id == client_id,
            Integration.provider == IntegrationProvider.GSC,
        )
        .one_or_none()
    )
    if integration is None:
        raise RuntimeError("GSC integration row missing")
    if not client_has_google_credentials(db, client_id):
        raise RuntimeError("GSC is not connected (missing credentials)")
    if not integration.external_property_id:
        raise RuntimeError("GSC property is not selected")
    return integration


def gsc_site_urls_for_integration(integration: Integration) -> list[str]:
    primary = (integration.external_property_id or "").strip()
    if not primary:
        return []
    sites = [primary]
    for secondary in _normalize_secondary_urls(integration.gsc_secondary_site_urls):
        if secondary != primary and secondary not in sites:
            sites.append(secondary)
    return sites


STAGING_CHUNK = 5000
#: Lean pulls keep day-by-day detail for this many recent days and one row per month before that. The engine, the results
#: loop and the keyword work look at 28 or 90 days, or whole calendar months, so older days are never read one by one.
LEAN_DAILY_DAYS = 120


def _is_lean(db: Session, job: SyncJob) -> bool:
    client = db.get(Client, job.client_id)
    return bool(client and client.gsc_lean_pull)


def lean_windows(start: date, end: date) -> tuple[tuple[date, date], list[tuple[date, date]]]:
    """The recent stretch to pull daily, and the older stretch cut into calendar months (the first may start mid-month,
    the last may end where the daily stretch begins)."""
    cutoff = end - timedelta(days=LEAN_DAILY_DAYS - 1)
    daily = (max(start, cutoff), end)
    months: list[tuple[date, date]] = []
    last_old = cutoff - timedelta(days=1)
    day = start
    while day <= last_old:
        month_end = date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])
        months.append((day, min(month_end, last_old)))
        day = month_end + timedelta(days=1)
    return daily, months


def _stage(db: Session, model: type, rows: Iterator[dict]) -> int:
    """Insert staged rows in chunks as they arrive: one compiled statement, and never more than a chunk in memory."""
    written = 0
    chunk: list[dict] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) >= STAGING_CHUNK:
            db.execute(insert(model), chunk)
            written += len(chunk)
            chunk = []
    if chunk:
        db.execute(insert(model), chunk)
        written += len(chunk)
    return written


def _metric(row: dict, key: str) -> Decimal:
    return Decimal(str(row.get(key) or 0))


def fetch_gsc_pages(db: Session, job: SyncJob) -> int:
    integration = _load_gsc_integration(db, job.client_id)
    token = access_token_for_client(db, job.client_id)
    site_urls = gsc_site_urls_for_integration(integration)
    lean = _is_lean(db, job)
    # Lean leaves out country and device: nothing reads them, and a page already has one row per day without them.
    dimensions = ["date", "page"] if lean else ["date", "page", "country", "device"]

    db.query(StagingGscPage).filter(StagingGscPage.job_id == job.id).delete()
    written = 0
    for site_url in site_urls:
        rows = query_search_analytics(
            access_token=token,
            site_url=site_url,
            start_date=job.start_date,
            end_date=job.end_date,
            dimensions=dimensions,
        )

        def staged(rows=rows, site_url=site_url):
            for row in rows:
                keys = row.get("keys") or []
                if len(keys) < len(dimensions):
                    continue
                yield {
                    "job_id": job.id,
                    "client_id": job.client_id,
                    "raw": row,
                    "date": date.fromisoformat(str(keys[0])),
                    "page": str(keys[1]),
                    "country": "" if lean else str(keys[2] or ""),
                    "device": "" if lean else str(keys[3] or ""),
                    "gsc_site_url": site_url,
                    "impressions": _metric(row, "impressions"),
                    "clicks": _metric(row, "clicks"),
                    "ctr": _metric(row, "ctr"),
                    "average_position": _metric(row, "position"),
                }

        written += _stage(db, StagingGscPage, staged())
    db.commit()
    return written


def fetch_gsc_daily(db: Session, job: SyncJob) -> int:
    integration = _load_gsc_integration(db, job.client_id)
    token = access_token_for_client(db, job.client_id)
    site_urls = gsc_site_urls_for_integration(integration)

    db.query(StagingGscDaily).filter(StagingGscDaily.job_id == job.id).delete()
    written = 0
    for site_url in site_urls:
        rows = query_search_analytics(
            access_token=token,
            site_url=site_url,
            start_date=job.start_date,
            end_date=job.end_date,
            dimensions=["date"],
        )

        def staged(rows=rows, site_url=site_url):
            for row in rows:
                keys = row.get("keys") or []
                if len(keys) < 1:
                    continue
                yield {
                    "job_id": job.id,
                    "client_id": job.client_id,
                    "raw": row,
                    "date": date.fromisoformat(str(keys[0])),
                    "gsc_site_url": site_url,
                    "impressions": _metric(row, "impressions"),
                    "clicks": _metric(row, "clicks"),
                    "ctr": _metric(row, "ctr"),
                    "average_position": _metric(row, "position"),
                }

        written += _stage(db, StagingGscDaily, staged())
    db.commit()
    return written


def fetch_gsc_queries(db: Session, job: SyncJob) -> int:
    integration = _load_gsc_integration(db, job.client_id)
    token = access_token_for_client(db, job.client_id)
    site_urls = gsc_site_urls_for_integration(integration)
    lean = _is_lean(db, job)

    db.query(StagingGscQueryPage).filter(StagingGscQueryPage.job_id == job.id).delete()
    written = 0
    for site_url in site_urls:
        if lean:
            daily, months = lean_windows(job.start_date, job.end_date)
            # (window, dimensions, whether each row carries its own date). An older month is one row per search and page,
            # dated the first day of its window.
            plan = [(daily, ["date", "query", "page"], True)] + [(window, ["query", "page"], False) for window in months]
        else:
            plan = [((job.start_date, job.end_date), ["date", "query", "page", "country", "device"], True)]

        for (window_start, window_end), dimensions, dated in plan:
            rows = query_search_analytics(
                access_token=token,
                site_url=site_url,
                start_date=window_start,
                end_date=window_end,
                dimensions=dimensions,
            )

            def staged(rows=rows, site_url=site_url, dimensions=dimensions, dated=dated, window_start=window_start):
                offset = 0 if dated else -1  # where the query sits in the keys is one place earlier without a date
                for row in rows:
                    keys = row.get("keys") or []
                    if len(keys) < len(dimensions):
                        continue
                    query = str(keys[1 + offset] or "").strip()
                    if not query:
                        # Never stage blank queries as query records.
                        continue
                    yield {
                        "job_id": job.id,
                        "client_id": job.client_id,
                        "raw": row,
                        "date": date.fromisoformat(str(keys[0])) if dated else window_start,
                        "query": query,
                        "page": str(keys[2 + offset]),
                        "country": "" if lean else str(keys[3] or ""),
                        "device": "" if lean else str(keys[4] or ""),
                        "gsc_site_url": site_url,
                        "impressions": _metric(row, "impressions"),
                        "clicks": _metric(row, "clicks"),
                        "ctr": _metric(row, "ctr"),
                        "average_position": _metric(row, "position"),
                    }

            written += _stage(db, StagingGscQueryPage, staged())
    db.commit()
    return written
