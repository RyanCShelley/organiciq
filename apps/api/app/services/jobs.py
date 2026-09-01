from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.job import SyncJob, SyncJobStatus
from app.schemas import SyncJobCreate


class OverlappingJobError(Exception):
    pass


def enqueue_sync_job(db: Session, client_id: UUID, payload: SyncJobCreate) -> SyncJob:
    if payload.end_date < payload.start_date:
        raise ValueError("end_date must be on or after start_date")

    job = SyncJob(
        client_id=client_id,
        source=payload.source,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=SyncJobStatus.QUEUED,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise OverlappingJobError(
            f"An active sync job already exists for client={client_id} source={payload.source}"
        ) from exc
    db.refresh(job)
    return job


def list_sync_jobs(db: Session, client_id: UUID, limit: int = 50) -> list[SyncJob]:
    return (
        db.query(SyncJob)
        .filter(SyncJob.client_id == client_id)
        .order_by(SyncJob.created_at.desc())
        .limit(limit)
        .all()
    )


def claim_next_job(db: Session) -> SyncJob | None:
    job = (
        db.query(SyncJob)
        .filter(SyncJob.status == SyncJobStatus.QUEUED)
        .order_by(SyncJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        return None

    job.status = SyncJobStatus.FETCHING
    job.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def mark_job_failed(db: Session, job: SyncJob, message: str) -> SyncJob:
    job.status = SyncJobStatus.FAILED
    job.error_message = message
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def _job_handlers() -> dict[str, object]:
    from app.ingestion.ga4.pipeline import run_ga4_job
    from app.ingestion.gsc.pipeline import run_gsc_pages_job, run_gsc_queries_job
    from app.ingestion.seranking.pipeline import run_seranking_search_job
    from app.ingestion.seranking.pipeline_ai import run_seranking_ai_job
    from app.ingestion.seranking.pipeline_audit import run_seranking_audit_job

    return {
        "gsc_pages": run_gsc_pages_job,
        "gsc_queries": run_gsc_queries_job,
        "ga4": run_ga4_job,
        "se_ranking_search": run_seranking_search_job,
        "se_ranking_ai": run_seranking_ai_job,
        "se_ranking_audit": run_seranking_audit_job,
    }


def process_job(db: Session, job: SyncJob) -> SyncJob:
    handler = _job_handlers().get(job.source)
    if handler is None:
        return mark_job_failed(db, job, f"Unknown source: {job.source}")
    return handler(db, job)  # type: ignore[operator]


def default_14_day_window() -> tuple[date, date]:
    end = date.today()
    start = date.fromordinal(end.toordinal() - 13)
    return start, end
