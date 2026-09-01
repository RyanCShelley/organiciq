from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.crawl import FactCrawlPageSnapshot, StagingSerAuditPage
from app.models.job import SyncJob


def publish_seranking_audit(db: Session, job: SyncJob) -> int:
    staging_rows = (
        db.query(StagingSerAuditPage)
        .filter(StagingSerAuditPage.job_id == job.id, StagingSerAuditPage.client_id == job.client_id)
        .all()
    )
    if not staging_rows:
        return 0

    snapshot_date = staging_rows[0].snapshot_date
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
        for row in staging_rows
    ]
    db.bulk_save_objects(facts)
    db.commit()
    return len(facts)


def clear_staging_for_job(db: Session, job_id: UUID) -> None:
    db.query(StagingSerAuditPage).filter(StagingSerAuditPage.job_id == job_id).delete()
    db.commit()
