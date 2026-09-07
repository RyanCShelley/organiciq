from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.crawl import FactCrawlPageSnapshot, StagingSerAuditPage
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


def publish_seranking_audit(db: Session, job: SyncJob) -> int:
    staging_rows = (
        db.query(StagingSerAuditPage)
        .filter(StagingSerAuditPage.job_id == job.id, StagingSerAuditPage.client_id == job.client_id)
        .all()
    )
    if not staging_rows:
        return 0

    snapshot_date = staging_rows[0].snapshot_date
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
        )
        for row in deduped
    ]
    db.bulk_save_objects(facts)
    db.commit()
    return len(facts)


def clear_staging_for_job(db: Session, job_id: UUID) -> None:
    db.query(StagingSerAuditPage).filter(StagingSerAuditPage.job_id == job_id).delete()
    db.commit()
