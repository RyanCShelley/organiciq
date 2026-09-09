from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.ingestion.seranking.fetch_audit import fetch_seranking_audit
from app.ingestion.seranking.publish_audit import clear_staging_for_job, publish_seranking_audit
from app.models.integration import Integration, IntegrationProvider
from app.models.job import DataWatermark, SyncJob, SyncJobStatus, ValidationStatus


class ValidationError(Exception):
    pass


def _set_status(db: Session, job: SyncJob, status: SyncJobStatus) -> None:
    job.status = status
    db.commit()


def _upsert_watermark(
    db: Session,
    *,
    client_id,
    fact_through: date | None,
    validation_status: ValidationStatus,
) -> None:
    row = (
        db.query(DataWatermark)
        .filter(DataWatermark.client_id == client_id, DataWatermark.source == "se_ranking_audit")
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if row is None:
        db.add(
            DataWatermark(
                client_id=client_id,
                source="se_ranking_audit",
                fact_through_date=fact_through,
                last_successful_sync_at=now if validation_status == ValidationStatus.PASSED else None,
                validation_status=validation_status,
            )
        )
    else:
        row.fact_through_date = fact_through
        row.validation_status = validation_status
        if validation_status == ValidationStatus.PASSED:
            row.last_successful_sync_at = now
    db.commit()


def _touch_integration(db: Session, client_id, *, success: bool, fact_date: date | None, error: str | None) -> None:
    integration = (
        db.query(Integration)
        .filter(Integration.client_id == client_id, Integration.provider == IntegrationProvider.SE_RANKING)
        .one_or_none()
    )
    if integration is None:
        return
    now = datetime.now(timezone.utc)
    integration.last_sync_completed = now
    if success:
        integration.last_successful_sync = now
        integration.last_fact_date = fact_date
        integration.error_message = None
    else:
        integration.error_message = error
    db.commit()


def run_seranking_audit_job(db: Session, job: SyncJob) -> SyncJob:
    try:
        integration = (
            db.query(Integration)
            .filter(
                Integration.client_id == job.client_id,
                Integration.provider == IntegrationProvider.SE_RANKING,
            )
            .one_or_none()
        )
        if integration:
            integration.last_sync_started = datetime.now(timezone.utc)
            db.commit()

        _set_status(db, job, SyncJobStatus.FETCHING)
        pages_fetched, pages_staged, issues_staged, audit_id, snapshot_date_text = fetch_seranking_audit(
            db, job
        )
        job.records_fetched = pages_fetched + issues_staged

        _set_status(db, job, SyncJobStatus.STAGING)
        _set_status(db, job, SyncJobStatus.NORMALIZING)
        pages_written, issues_written = publish_seranking_audit(db, job)
        job.records_written = pages_written + issues_written

        _set_status(db, job, SyncJobStatus.VALIDATING)
        if pages_written == 0:
            raise ValidationError(
                f"SE Ranking Website Audit {audit_id} returned no crawl pages to publish"
            )

        snapshot_date = date.fromisoformat(snapshot_date_text)
        job.fact_watermark = snapshot_date
        job.validation_status = ValidationStatus.PASSED
        job.status = SyncJobStatus.SUCCESSFUL
        job.error_message = (
            f"Published audit {audit_id} snapshot {snapshot_date.isoformat()} "
            f"({pages_written} pages, {issues_written} issue rows"
            f"{f', staged {pages_staged}' if pages_staged else ''})"
        )
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        clear_staging_for_job(db, job.id)
        _upsert_watermark(
            db,
            client_id=job.client_id,
            fact_through=snapshot_date,
            validation_status=ValidationStatus.PASSED,
        )
        _touch_integration(
            db,
            job.client_id,
            success=True,
            fact_date=snapshot_date,
            error=job.error_message,
        )
        return job
    except Exception as exc:  # noqa: BLE001
        job.status = SyncJobStatus.FAILED
        job.validation_status = ValidationStatus.FAILED
        job.error_message = str(exc)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        clear_staging_for_job(db, job.id)
        _upsert_watermark(
            db,
            client_id=job.client_id,
            fact_through=None,
            validation_status=ValidationStatus.FAILED,
        )
        _touch_integration(db, job.client_id, success=False, fact_date=None, error=str(exc))
        return job
