from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.job import SyncJob, SyncJobStatus
from app.schemas import SyncJobCreate

ACTIVE_JOB_STATUSES = (
    SyncJobStatus.QUEUED,
    SyncJobStatus.FETCHING,
    SyncJobStatus.STAGING,
    SyncJobStatus.NORMALIZING,
    SyncJobStatus.VALIDATING,
)

# Audit pulls can be large; still fail jobs that clearly hung after a deploy/crash.
STALE_ACTIVE_JOB_MINUTES = 45


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


def list_active_jobs(db: Session, client_id: UUID | None = None) -> list[SyncJob]:
    query = db.query(SyncJob).filter(SyncJob.status.in_(ACTIVE_JOB_STATUSES))
    if client_id is not None:
        query = query.filter(SyncJob.client_id == client_id)
    return query.order_by(SyncJob.created_at.asc()).all()


def cancel_active_jobs(
    db: Session,
    client_id: UUID,
    *,
    message: str = "Cancelled by user",
) -> list[SyncJob]:
    jobs = list_active_jobs(db, client_id)
    now = datetime.now(timezone.utc)
    for job in jobs:
        job.status = SyncJobStatus.FAILED
        job.error_message = message
        job.completed_at = now
    if jobs:
        db.commit()
        for job in jobs:
            db.refresh(job)
    return jobs


def fail_stale_active_jobs(
    db: Session,
    *,
    max_age_minutes: int = STALE_ACTIVE_JOB_MINUTES,
) -> list[SyncJob]:
    """Mark hung active jobs failed so Sync All / enqueue can proceed after worker crashes."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    jobs = list_active_jobs(db)
    stale: list[SyncJob] = []
    now = datetime.now(timezone.utc)
    for job in jobs:
        anchor = job.started_at or job.updated_at or job.created_at
        if anchor is None:
            continue
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
        if anchor > cutoff:
            continue
        job.status = SyncJobStatus.FAILED
        job.error_message = (
            f"Timed out after {max_age_minutes} minutes while syncing (stuck job cleared)"
        )
        job.completed_at = now
        stale.append(job)
    if stale:
        db.commit()
        for job in stale:
            db.refresh(job)
    return stale


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
