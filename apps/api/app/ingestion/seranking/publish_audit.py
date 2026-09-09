from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.crawl import (
    FactCrawlPageIssue,
    FactCrawlPageSnapshot,
    StagingSerAuditIssue,
    StagingSerAuditPage,
)
from app.models.job import SyncJob


def _pick_better_row(current: StagingSerAuditPage, incoming: StagingSerAuditPage) -> StagingSerAuditPage:
    """When audit returns URL variants that normalize the same, keep the richer row."""
    current_status = current.status_code or 0
    incoming_status = incoming.status_code or 0
    if incoming_status == 200 and current_status != 200:
        return incoming
    if current_status == 200 and incoming_status != 200:
        return current
    if incoming.word_count > current.word_count:
        return incoming
    if incoming.word_count < current.word_count:
        return current
    if incoming.inbound_internal_links > current.inbound_internal_links:
        return incoming
    return current


def _dedupe_staging_rows(rows: list[StagingSerAuditPage]) -> list[StagingSerAuditPage]:
    by_url: dict[str, StagingSerAuditPage] = {}
    for row in rows:
        if not row.normalized_url:
            continue
        existing = by_url.get(row.normalized_url)
        if existing is None:
            by_url[row.normalized_url] = row
        else:
            by_url[row.normalized_url] = _pick_better_row(existing, row)
    return list(by_url.values())


def publish_seranking_audit(db: Session, job: SyncJob) -> tuple[int, int]:
    """Publish page snapshots + issue codes. Returns (pages_written, issues_written)."""
    staging_rows = (
        db.query(StagingSerAuditPage)
        .filter(StagingSerAuditPage.job_id == job.id, StagingSerAuditPage.client_id == job.client_id)
        .all()
    )
    issue_rows = (
        db.query(StagingSerAuditIssue)
        .filter(StagingSerAuditIssue.job_id == job.id, StagingSerAuditIssue.client_id == job.client_id)
        .all()
    )
    if not staging_rows and not issue_rows:
        return 0, 0

    snapshot_date = (staging_rows or issue_rows)[0].snapshot_date
    pages_written = 0
    if staging_rows:
        deduped = _dedupe_staging_rows(staging_rows)
        db.query(FactCrawlPageSnapshot).filter(FactCrawlPageSnapshot.client_id == job.client_id).delete()
        facts = [
            FactCrawlPageSnapshot(
                client_id=job.client_id,
                snapshot_date=snapshot_date,
                raw_url=row.raw_url,
                normalized_url=row.normalized_url,
                indexable=row.indexable,
                status_code=row.status_code,
                canonical_url=row.canonical_url,
                inbound_internal_links=row.inbound_internal_links,
                word_count=row.word_count,
                in_sitemap=row.in_sitemap,
                title=row.title,
                description=row.description,
                title_duplicate=row.title_duplicate,
                description_duplicate=row.description_duplicate,
                robots=row.robots,
                blocked_by_robots=row.blocked_by_robots,
                redirect_url=row.redirect_url,
                redirect_count=row.redirect_count,
            )
            for row in deduped
        ]
        db.bulk_save_objects(facts)
        pages_written = len(facts)

    db.query(FactCrawlPageIssue).filter(FactCrawlPageIssue.client_id == job.client_id).delete()
    issue_facts = [
        FactCrawlPageIssue(
            client_id=job.client_id,
            snapshot_date=row.snapshot_date,
            issue_code=row.issue_code,
            normalized_url=row.normalized_url,
            severity=row.severity,
            raw=row.raw or {},
        )
        for row in issue_rows
    ]
    if issue_facts:
        db.bulk_save_objects(issue_facts)
    db.commit()
    return pages_written, len(issue_facts)


def clear_staging_for_job(db: Session, job_id: UUID) -> None:
    db.query(StagingSerAuditPage).filter(StagingSerAuditPage.job_id == job_id).delete()
    db.query(StagingSerAuditIssue).filter(StagingSerAuditIssue.job_id == job_id).delete()
    db.commit()
