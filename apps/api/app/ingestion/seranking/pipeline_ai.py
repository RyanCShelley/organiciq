from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ingestion.seranking.fetch_ai import fetch_seranking_ai, fetch_seranking_ai_tracker_stats
from app.ingestion.seranking.publish_ai import publish_seranking_ai, publish_seranking_ai_tracker_stats
from app.models.integration import Integration, IntegrationProvider
from app.models.job import DataWatermark, SyncJob, SyncJobStatus, ValidationStatus
from app.models.seranking import FactSerAiCheck, FactSerAiPrompt


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
        .filter(DataWatermark.client_id == client_id, DataWatermark.source == "se_ranking_ai")
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if row is None:
        db.add(
            DataWatermark(
                client_id=client_id,
                source="se_ranking_ai",
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


def run_seranking_ai_job(db: Session, job: SyncJob) -> SyncJob:
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
        prompts_fetched, checks_fetched = fetch_seranking_ai(db, job)
        tracker_stats_fetched = fetch_seranking_ai_tracker_stats(db, job)
        job.records_fetched = prompts_fetched + checks_fetched + tracker_stats_fetched

        _set_status(db, job, SyncJobStatus.STAGING)
        _set_status(db, job, SyncJobStatus.NORMALIZING)
        prompts_written, checks_written = publish_seranking_ai(db, job)
        tracker_stats_written = publish_seranking_ai_tracker_stats(db, job)
        job.records_written = prompts_written + checks_written + tracker_stats_written

        _set_status(db, job, SyncJobStatus.VALIDATING)
        max_check = (
            db.query(func.max(FactSerAiCheck.date))
            .filter(
                FactSerAiCheck.client_id == job.client_id,
                FactSerAiCheck.date >= job.start_date,
                FactSerAiCheck.date <= job.end_date,
            )
            .scalar()
        )
        prompt_count = (
            db.query(func.count(FactSerAiPrompt.id))
            .filter(FactSerAiPrompt.client_id == job.client_id)
            .scalar()
        )

        if max_check is None and job.records_fetched == 0 and not prompt_count:
            raise ValidationError("No SE Ranking AI prompts or checks returned")

        if max_check is None:
            max_check = job.end_date

        job.fact_watermark = max_check
        if max_check < job.end_date:
            job.validation_status = ValidationStatus.PASSED
            job.status = SyncJobStatus.PARTIAL
            job.error_message = (
                f"SE Ranking AI checks available through {max_check.isoformat()}, "
                f"requested end {job.end_date.isoformat()}"
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
            fact_through=max_check,
            validation_status=ValidationStatus.PASSED,
        )
        _touch_integration(
            db,
            job.client_id,
            success=True,
            fact_date=max_check,
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
