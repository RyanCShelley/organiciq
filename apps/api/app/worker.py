import importlib
import logging
import time

from app.core.db import SessionLocal
from app.core.settings import get_settings
from app.models.job import SyncJob

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("organiciq.worker")


def _jobs_module():
    """Reload job dispatch each cycle so worker picks up code changes without a manual restart."""
    import sys

    from app.services import jobs

    importlib.reload(jobs)
    for module_name in (
        "app.ingestion.google_auth",
        "app.ingestion.google_credentials",
        "app.ingestion.gsc.fetch",
        "app.ingestion.gsc.publish",
        "app.ingestion.gsc.pipeline",
        "app.ingestion.ga4.fetch",
        "app.ingestion.ga4.pipeline",
        "app.ingestion.seranking.client",
        "app.ingestion.seranking.audit_pages",
        "app.ingestion.seranking.fetch_audit",
        "app.ingestion.seranking.publish_audit",
        "app.ingestion.seranking.pipeline_audit",
    ):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        try:
            importlib.reload(module)
        except Exception:
            logger.exception("Hot reload failed for %s; restart worker after model changes", module_name)
    return jobs


def run_once() -> bool:
    jobs = _jobs_module()
    db = SessionLocal()
    try:
        job = jobs.claim_next_job(db)
        if job is None:
            return False
        job_id = job.id
        logger.info("Processing job %s source=%s client=%s", job_id, job.source, job.client_id)
        try:
            result = jobs.process_job(db, job)
            logger.info("Job %s finished status=%s", job_id, result.status.value)
        except Exception:  # noqa: BLE001 — worker must not crash on one bad job
            db.rollback()
            logger.exception("Job %s failed with unhandled exception", job_id)
            job = db.get(SyncJob, job_id)
            if job is not None:
                jobs.mark_job_failed(db, job, "Unhandled worker error — see worker logs")
        return True
    finally:
        db.close()


def _maybe_daily_sync() -> None:
    from app.services import daily_sync

    db = SessionLocal()
    try:
        daily_sync.maybe_run_daily_sync(db)
    except Exception:  # noqa: BLE001 — scheduler must not stop the worker
        db.rollback()
        logger.exception("Daily sync scheduler failed")
    finally:
        db.close()


def main() -> None:
    settings = get_settings()
    logger.info(
        "Organic IQ worker started (poll=%.1fs, daily_sync=%s hour_utc=%s lookback=%sd)",
        settings.worker_poll_interval_seconds,
        settings.daily_sync_enabled,
        settings.daily_sync_hour_utc,
        settings.daily_sync_lookback_days,
    )
    while True:
        _maybe_daily_sync()
        worked = run_once()
        if not worked:
            time.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    main()
