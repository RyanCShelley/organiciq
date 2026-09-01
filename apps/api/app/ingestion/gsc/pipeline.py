from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.ingestion.gsc.fetch import fetch_gsc_daily, fetch_gsc_pages, fetch_gsc_queries
from app.ingestion.gsc.publish import publish_gsc_daily, publish_gsc_pages, publish_gsc_queries
from app.ingestion.gsc.validate import ValidationError, validate_gsc_pages, validate_gsc_queries
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.models.job import DataWatermark, SyncJob, SyncJobStatus, ValidationStatus


def _set_status(db: Session, job: SyncJob, status: SyncJobStatus) -> None:
    job.status = status
    db.commit()


def _upsert_watermark(
    db: Session,
    *,
    client_id,
    source: str,
    fact_through: date | None,
    validation_status: ValidationStatus,
) -> None:
    row = (
        db.query(DataWatermark)
        .filter(DataWatermark.client_id == client_id, DataWatermark.source == source)
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = DataWatermark(
            client_id=client_id,
            source=source,
            fact_through_date=fact_through,
            last_successful_sync_at=now if validation_status == ValidationStatus.PASSED else None,
            validation_status=validation_status,
        )
        db.add(row)
    else:
        row.fact_through_date = fact_through
        row.validation_status = validation_status
        if validation_status == ValidationStatus.PASSED:
            row.last_successful_sync_at = now
    db.commit()


def _fail_gsc_job(db: Session, job: SyncJob, *, source: str, exc: Exception) -> SyncJob:
    job_id = job.id
    client_id = job.client_id
    message = str(exc)[:2000]
    db.rollback()
    job = db.get(SyncJob, job_id)
    if job is None:
        raise exc
    job.status = SyncJobStatus.FAILED
    job.validation_status = ValidationStatus.FAILED
    job.error_message = message
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    _upsert_watermark(
        db,
        client_id=client_id,
        source=source,
        fact_through=None,
        validation_status=ValidationStatus.FAILED,
    )
    _touch_integration(db, client_id, success=False, fact_date=None, error=message)
    return job


def _touch_integration(db: Session, client_id, *, success: bool, fact_date: date | None, error: str | None) -> None:
    integration = (
        db.query(Integration)
        .filter(Integration.client_id == client_id, Integration.provider == IntegrationProvider.GSC)
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
        integration.connection_status = ConnectionStatus.CONNECTED
    else:
        integration.error_message = error
        if error and ("401 Unauthorized" in error or "invalid_grant" in error.lower()):
            integration.connection_status = ConnectionStatus.ERROR
    db.commit()


def run_gsc_pages_job(db: Session, job: SyncJob) -> SyncJob:
    try:
        integration = (
            db.query(Integration)
            .filter(Integration.client_id == job.client_id, Integration.provider == IntegrationProvider.GSC)
            .one_or_none()
        )
        if integration:
            integration.last_sync_started = datetime.now(timezone.utc)
            db.commit()

        _set_status(db, job, SyncJobStatus.FETCHING)
        fetched_pages = fetch_gsc_pages(db, job)
        fetched_daily = fetch_gsc_daily(db, job)
        job.records_fetched = fetched_pages + fetched_daily

        _set_status(db, job, SyncJobStatus.STAGING)
        _set_status(db, job, SyncJobStatus.NORMALIZING)
        written_pages = publish_gsc_pages(db, job)
        written_daily = publish_gsc_daily(db, job)
        job.records_written = written_pages + written_daily

        _set_status(db, job, SyncJobStatus.VALIDATING)
        max_date = validate_gsc_pages(db, job, fetched_pages, written_pages)

        if max_date is None and fetched_pages == 0 and fetched_daily == 0:
            # Empty window can be valid (new property); watermark to end_date only if API succeeded.
            job.validation_status = ValidationStatus.PASSED
            job.fact_watermark = job.end_date
            job.status = SyncJobStatus.SUCCESSFUL
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            _upsert_watermark(
                db,
                client_id=job.client_id,
                source="gsc_pages",
                fact_through=job.end_date,
                validation_status=ValidationStatus.PASSED,
            )
            _touch_integration(db, job.client_id, success=True, fact_date=job.end_date, error=None)
            return job

        if max_date is None:
            raise ValidationError("No fact dates after publish")

        job.fact_watermark = max_date
        if max_date < job.end_date:
            job.validation_status = ValidationStatus.PASSED
            job.status = SyncJobStatus.PARTIAL
            job.error_message = (
                f"GSC data available through {max_date.isoformat()}, "
                f"requested end {job.end_date.isoformat()} (common GSC lag)"
            )
        else:
            job.validation_status = ValidationStatus.PASSED
            job.status = SyncJobStatus.SUCCESSFUL
            job.error_message = None

        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        _upsert_watermark(
            db,
            client_id=job.client_id,
            source="gsc_pages",
            fact_through=max_date,
            validation_status=ValidationStatus.PASSED,
        )
        _touch_integration(
            db,
            job.client_id,
            success=job.status in {SyncJobStatus.SUCCESSFUL, SyncJobStatus.PARTIAL},
            fact_date=max_date,
            error=job.error_message,
        )
        return job
    except Exception as exc:  # noqa: BLE001 — durable job failure boundary
        return _fail_gsc_job(db, job, source="gsc_pages", exc=exc)


def run_gsc_queries_job(db: Session, job: SyncJob) -> SyncJob:
    try:
        integration = (
            db.query(Integration)
            .filter(Integration.client_id == job.client_id, Integration.provider == IntegrationProvider.GSC)
            .one_or_none()
        )
        if integration:
            integration.last_sync_started = datetime.now(timezone.utc)
            db.commit()

        _set_status(db, job, SyncJobStatus.FETCHING)
        fetched = fetch_gsc_queries(db, job)
        job.records_fetched = fetched

        _set_status(db, job, SyncJobStatus.STAGING)
        _set_status(db, job, SyncJobStatus.NORMALIZING)
        written = publish_gsc_queries(db, job)
        job.records_written = written

        _set_status(db, job, SyncJobStatus.VALIDATING)
        max_date = validate_gsc_queries(db, job, fetched, written)

        if max_date is None and fetched == 0:
            job.validation_status = ValidationStatus.PASSED
            job.fact_watermark = job.end_date
            job.status = SyncJobStatus.SUCCESSFUL
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            _upsert_watermark(
                db,
                client_id=job.client_id,
                source="gsc_queries",
                fact_through=job.end_date,
                validation_status=ValidationStatus.PASSED,
            )
            _touch_integration(db, job.client_id, success=True, fact_date=job.end_date, error=None)
            return job

        if max_date is None:
            raise ValidationError("No query fact dates after publish")

        job.fact_watermark = max_date
        if max_date < job.end_date:
            job.validation_status = ValidationStatus.PASSED
            job.status = SyncJobStatus.PARTIAL
            job.error_message = (
                f"GSC query data available through {max_date.isoformat()}, "
                f"requested end {job.end_date.isoformat()} (common GSC lag)"
            )
        else:
            job.validation_status = ValidationStatus.PASSED
            job.status = SyncJobStatus.SUCCESSFUL
            job.error_message = None

        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        _upsert_watermark(
            db,
            client_id=job.client_id,
            source="gsc_queries",
            fact_through=max_date,
            validation_status=ValidationStatus.PASSED,
        )
        _touch_integration(
            db,
            job.client_id,
            success=job.status in {SyncJobStatus.SUCCESSFUL, SyncJobStatus.PARTIAL},
            fact_date=max_date,
            error=job.error_message,
        )
        return job
    except Exception as exc:  # noqa: BLE001
        return _fail_gsc_job(db, job, source="gsc_queries", exc=exc)
