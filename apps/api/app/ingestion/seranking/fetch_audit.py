from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.ingestion.seranking import client as ser_client
from app.ingestion.seranking.audit_pages import parse_audit_page, resolve_latest_finished_audit
from app.models.client import Client
from app.models.crawl import StagingSerAuditPage
from app.models.integration import Integration, IntegrationProvider
from app.models.job import SyncJob


def _api_key() -> str:
    key = get_settings().se_ranking_api_key.strip()
    if not key:
        raise RuntimeError("SE_RANKING_API_KEY not configured")
    return key


def _load_integration(db: Session, client_id: UUID) -> Integration:
    integration = (
        db.query(Integration)
        .filter(
            Integration.client_id == client_id,
            Integration.provider == IntegrationProvider.SE_RANKING,
        )
        .one_or_none()
    )
    if integration is None:
        raise RuntimeError("SE Ranking integration row missing")
    if not integration.external_property_id:
        raise RuntimeError("SE Ranking project is not selected")
    return integration


def fetch_seranking_audit(db: Session, job: SyncJob) -> tuple[int, int, str, str]:
    integration = _load_integration(db, job.client_id)
    client = db.query(Client).filter(Client.id == job.client_id).one()
    api_key = _api_key()

    audit_id, snapshot_date = resolve_latest_finished_audit(
        api_key=api_key,
        site_id=integration.external_property_id,
        client_domain=client.domain,
    )
    status = ser_client.get_audit_status(api_key=api_key, audit_id=audit_id)
    audit_status = str(status.get("status") or "").strip().lower()
    if audit_status and audit_status != "finished":
        raise RuntimeError(
            f"SE Ranking Website Audit {audit_id} is {audit_status or 'unknown'}; wait for it to finish"
        )

    pages = ser_client.list_audit_pages_paginated(api_key=api_key, audit_id=audit_id)
    rows: list[StagingSerAuditPage] = []
    for page in pages:
        parsed = parse_audit_page(page)
        if not parsed["normalized_url"]:
            continue
        rows.append(
            StagingSerAuditPage(
                job_id=job.id,
                client_id=job.client_id,
                audit_id=str(audit_id),
                snapshot_date=snapshot_date,
                raw=page,
                **parsed,
            )
        )

    if rows:
        db.bulk_save_objects(rows)
    db.commit()
    return len(pages), len(rows), str(audit_id), snapshot_date.isoformat()
