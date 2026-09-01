from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ingestion.ga4.fetch import fetch_ga4
from app.ingestion.ga4.publish import publish_ga4
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
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
        .filter(DataWatermark.client_id == client_id, DataWatermark.source == "ga4")
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if row is None:
        db.add(
            DataWatermark(
                client_id=client_id,
                source="ga4",
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
        .filter(Integration.client_id == client_id, Integration.provider == IntegrationProvider.GA4)
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


def run_ga4_job(db: Session, job: SyncJob) -> SyncJob:
    try:
        integration = (
            db.query(Integration)
            .filter(Integration.client_id == job.client_id, Integration.provider == IntegrationProvider.GA4)
            .one_or_none()
        )
        if integration:
            integration.last_sync_started = datetime.now(timezone.utc)
            db.commit()

        _set_status(db, job, SyncJobStatus.FETCHING)
        traffic_fetched, event_fetched = fetch_ga4(db, job)
        job.records_fetched = traffic_fetched + event_fetched

        _set_status(db, job, SyncJobStatus.STAGING)
        _set_status(db, job, SyncJobStatus.NORMALIZING)
        traffic_written, event_written = publish_ga4(db, job)
        job.records_written = traffic_written + event_written

        _set_status(db, job, SyncJobStatus.VALIDATING)
        max_traffic = (
            db.query(func.max(FactGa4Traffic.date))
            .filter(
                FactGa4Traffic.client_id == job.client_id,
                FactGa4Traffic.date >= job.start_date,
                FactGa4Traffic.date <= job.end_date,
            )
            .scalar()
        )
        max_events = (
            db.query(func.max(FactGa4Event.date))
            .filter(
                FactGa4Event.client_id == job.client_id,
                FactGa4Event.date >= job.start_date,
                FactGa4Event.date <= job.end_date,
            )
            .scalar()
        )
        dates = [d for d in [max_traffic, max_events] if d is not None]
        max_date = max(dates) if dates else None

        if max_date is None and job.records_fetched == 0:
            job.validation_status = ValidationStatus.PASSED
            job.fact_watermark = job.end_date
            job.status = SyncJobStatus.SUCCESSFUL
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            _upsert_watermark(
                db,
                client_id=job.client_id,
                fact_through=job.end_date,
                validation_status=ValidationStatus.PASSED,
            )
            _touch_integration(db, job.client_id, success=True, fact_date=job.end_date, error=None)
            return job

        if max_date is None:
            raise ValidationError("No GA4 fact dates after publish")

        job.fact_watermark = max_date
        if max_date < job.end_date:
            job.validation_status = ValidationStatus.PASSED
            job.status = SyncJobStatus.PARTIAL
            job.error_message = (
                f"GA4 data available through {max_date.isoformat()}, "
                f"requested end {job.end_date.isoformat()} (common reporting lag)"
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
            fact_through=max_date,
            validation_status=ValidationStatus.PASSED,
        )
        _touch_integration(
            db,
            job.client_id,
            success=True,
            fact_date=max_date,
            error=job.error_message,
        )
        return job
    except Exception as exc:  # noqa: BLE001
        job.status = SyncJobStatus.FAILED
        job.validation_status = ValidationStatus.FAILED
        job.error_message = str(exc)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        _upsert_watermark(
            db,
            client_id=job.client_id,
            fact_through=None,
            validation_status=ValidationStatus.FAILED,
        )
        _touch_integration(db, job.client_id, success=False, fact_date=None, error=str(exc))
        return job
