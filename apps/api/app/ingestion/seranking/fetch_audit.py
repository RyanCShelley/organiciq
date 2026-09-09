from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.core.urls import normalize_url
from app.ingestion.seranking import client as ser_client
from app.ingestion.seranking.audit_pages import parse_audit_page, resolve_latest_finished_audit
from app.models.client import Client
from app.models.crawl import StagingSerAuditIssue, StagingSerAuditPage
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


def _issue_url(item: dict) -> str | None:
    for key in ("url", "page_url", "page", "path"):
        raw = str(item.get(key) or "").strip()
        if raw:
            return raw
    return None


def fetch_seranking_audit(db: Session, job: SyncJob) -> tuple[int, int, int, str, str]:
    """Fetch audit pages + curated issue codes.

    Returns (pages_fetched, pages_staged, issues_staged, audit_id, snapshot_date_iso).
    """
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
    page_rows: list[StagingSerAuditPage] = []
    for page in pages:
        parsed = parse_audit_page(page)
        if not parsed["normalized_url"]:
            continue
        page_rows.append(
            StagingSerAuditPage(
                job_id=job.id,
                client_id=job.client_id,
                audit_id=str(audit_id),
                snapshot_date=snapshot_date,
                raw=page,
                **parsed,
            )
        )

    issue_rows: list[StagingSerAuditIssue] = []
    for code in ser_client.AUDIT_ISSUE_CODES:
        try:
            items = ser_client.list_issue_pages_paginated(
                api_key=api_key,
                audit_id=audit_id,
                code=code,
            )
        except Exception:  # noqa: BLE001 — one bad code should not fail the whole audit
            continue
        if not items:
            # Site-level codes may return empty items but still be “present” via count endpoints.
            # Prefer explicit page/site markers only when the API returns rows.
            continue
        if code in ser_client.SITE_LEVEL_ISSUE_CODES:
            issue_rows.append(
                StagingSerAuditIssue(
                    job_id=job.id,
                    client_id=job.client_id,
                    audit_id=str(audit_id),
                    snapshot_date=snapshot_date,
                    issue_code=code,
                    normalized_url=None,
                    severity=None,
                    raw={"code": code, "items_count": len(items), "sample": items[:3]},
                )
            )
            continue
        for item in items:
            raw_url = _issue_url(item)
            normalized = normalize_url(raw_url) if raw_url else None
            if not normalized:
                continue
            issue_rows.append(
                StagingSerAuditIssue(
                    job_id=job.id,
                    client_id=job.client_id,
                    audit_id=str(audit_id),
                    snapshot_date=snapshot_date,
                    issue_code=code,
                    normalized_url=normalized,
                    severity=str(item.get("severity") or item.get("type") or "") or None,
                    raw=item,
                )
            )

    db.query(StagingSerAuditPage).filter(StagingSerAuditPage.job_id == job.id).delete()
    db.query(StagingSerAuditIssue).filter(StagingSerAuditIssue.job_id == job.id).delete()
    if page_rows:
        db.bulk_save_objects(page_rows)
    if issue_rows:
        db.bulk_save_objects(issue_rows)
    db.commit()
    return len(pages), len(page_rows), len(issue_rows), str(audit_id), snapshot_date.isoformat()
