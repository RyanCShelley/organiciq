from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.ingestion.google_credentials import access_token_for_client, client_has_google_credentials
from app.ingestion.gsc.client import query_search_analytics
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


def _metric(row: dict, key: str) -> Decimal:
    return Decimal(str(row.get(key) or 0))


def fetch_gsc_pages(db: Session, job: SyncJob) -> int:
    integration = _load_gsc_integration(db, job.client_id)
    token = access_token_for_client(db, job.client_id)
    site_urls = gsc_site_urls_for_integration(integration)

    db.query(StagingGscPage).filter(StagingGscPage.job_id == job.id).delete()
    written = 0
    for site_url in site_urls:
        rows = query_search_analytics(
            access_token=token,
            site_url=site_url,
            start_date=job.start_date,
            end_date=job.end_date,
            dimensions=["date", "page", "country", "device"],
        )
        for row in rows:
            keys = row.get("keys") or []
            if len(keys) < 4:
                continue
            db.add(
                StagingGscPage(
                    job_id=job.id,
                    client_id=job.client_id,
                    raw=row,
                    date=date.fromisoformat(str(keys[0])),
                    page=str(keys[1]),
                    country=str(keys[2] or ""),
                    device=str(keys[3] or ""),
                    gsc_site_url=site_url,
                    impressions=_metric(row, "impressions"),
                    clicks=_metric(row, "clicks"),
                    ctr=_metric(row, "ctr"),
                    average_position=_metric(row, "position"),
                )
            )
            written += 1
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
        for row in rows:
            keys = row.get("keys") or []
            if len(keys) < 1:
                continue
            db.add(
                StagingGscDaily(
                    job_id=job.id,
                    client_id=job.client_id,
                    raw=row,
                    date=date.fromisoformat(str(keys[0])),
                    gsc_site_url=site_url,
                    impressions=_metric(row, "impressions"),
                    clicks=_metric(row, "clicks"),
                    ctr=_metric(row, "ctr"),
                    average_position=_metric(row, "position"),
                )
            )
            written += 1
    db.commit()
    return written


def fetch_gsc_queries(db: Session, job: SyncJob) -> int:
    integration = _load_gsc_integration(db, job.client_id)
    token = access_token_for_client(db, job.client_id)
    site_urls = gsc_site_urls_for_integration(integration)

    db.query(StagingGscQueryPage).filter(StagingGscQueryPage.job_id == job.id).delete()
    written = 0
    for site_url in site_urls:
        rows = query_search_analytics(
            access_token=token,
            site_url=site_url,
            start_date=job.start_date,
            end_date=job.end_date,
            dimensions=["date", "query", "page", "country", "device"],
        )
        for row in rows:
            keys = row.get("keys") or []
            if len(keys) < 5:
                continue
            query = str(keys[1] or "").strip()
            if not query:
                # Never stage blank queries as query records.
                continue
            db.add(
                StagingGscQueryPage(
                    job_id=job.id,
                    client_id=job.client_id,
                    raw=row,
                    date=date.fromisoformat(str(keys[0])),
                    query=query,
                    page=str(keys[2]),
                    country=str(keys[3] or ""),
                    device=str(keys[4] or ""),
                    gsc_site_url=site_url,
                    impressions=_metric(row, "impressions"),
                    clicks=_metric(row, "clicks"),
                    ctr=_metric(row, "ctr"),
                    average_position=_metric(row, "position"),
                )
            )
            written += 1
    db.commit()
    return written
