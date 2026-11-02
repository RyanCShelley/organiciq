"""Pull a client's data from every connected source, and say where the pull stands.

The plan (what is pulled and how far back) is one function so the button, the queueing and the reset tool agree.
Progress comes from the client's sync jobs. A job reports its stage, not a percentage, and how long a source takes
depends on how much data the client has, so there is no time-left estimate: the status is what is measured (sources
done, the stage each is in, and how long a running one has been going).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.client_bing_site import ClientBingSite
from app.models.integration import Integration
from app.models.job import SyncJob, SyncJobStatus
from app.schemas import SyncJobCreate
from app.services.daily_sync import _PROVIDER_SOURCES
from app.services.jobs import OverlappingJobError, enqueue_sync_job

GSC_BACKFILL_MONTHS = 13
GA4_BACKFILL_MONTHS = 26

LABELS = {
    "gsc_pages": "Search Console: pages",
    "gsc_queries": "Search Console: searches",
    "ga4": "Google Analytics",
    "se_ranking_search": "SE Ranking: rankings",
    "se_ranking_ai": "SE Ranking: AI search",
    "site_crawl": "Site crawl",
    "bing_query_stats": "Bing Webmaster",
}
ACTIVE = (
    SyncJobStatus.QUEUED,
    SyncJobStatus.FETCHING,
    SyncJobStatus.STAGING,
    SyncJobStatus.NORMALIZING,
    SyncJobStatus.VALIDATING,
)
STAGE_TEXT = {
    SyncJobStatus.QUEUED: "Waiting its turn",
    SyncJobStatus.FETCHING: "Pulling from the source",
    SyncJobStatus.STAGING: "Saving what came back",
    SyncJobStatus.NORMALIZING: "Organising it",
    SyncJobStatus.VALIDATING: "Checking it",
    SyncJobStatus.SUCCESSFUL: "Done",
    SyncJobStatus.PARTIAL: "Done, with some gaps",
    SyncJobStatus.FAILED: "Failed",
}


def _sources_for_client(db: Session, client_id) -> set[str]:
    """Sources the client has a connection for. Unlike the daily sync this ignores the client's status, so a
    client still being set up can be pulled."""
    rows = (
        db.query(Integration.provider)
        .filter(Integration.client_id == client_id)
        .filter(Integration.external_property_id.isnot(None))
        .filter(Integration.external_property_id != "")
        .all()
    )
    out: set[str] = set()
    for (provider,) in rows:
        out.update(_PROVIDER_SOURCES.get(provider, ()))
    return out


def pull_plan(db: Session, client: Any, today: date | None = None) -> list[dict]:
    """What a pull would fetch, and how far back, for each source the client has connected."""
    today = today or date.today()
    plan: list[dict] = []
    for source in sorted(_sources_for_client(db, client.id)):
        if source.startswith("gsc"):
            start, end, reach = today - timedelta(days=30 * GSC_BACKFILL_MONTHS), today - timedelta(days=3), f"{GSC_BACKFILL_MONTHS} months of daily data"
        elif source == "ga4":
            start, end, reach = today - timedelta(days=30 * GA4_BACKFILL_MONTHS), today - timedelta(days=1), f"{GA4_BACKFILL_MONTHS} months of daily data"
        else:
            start, end, reach = today - timedelta(days=2), today, "today's snapshot"
        plan.append({"source": source, "start": start, "end": end, "reach": reach})
    if (client.domain or "").strip():
        plan.append({"source": "site_crawl", "start": today, "end": today, "reach": "the site as it is today"})
    if db.query(ClientBingSite).filter(ClientBingSite.client_id == client.id).first() is not None:
        plan.append({"source": "bing_query_stats", "start": today, "end": today, "reach": "everything Bing returns for the site"})
    for item in plan:
        item["label"] = LABELS.get(item["source"], item["source"])
    return plan


ORPHAN_SILENT_MINUTES = 10
RUNNING = (SyncJobStatus.FETCHING, SyncJobStatus.STAGING, SyncJobStatus.NORMALIZING, SyncJobStatus.VALIDATING)
RESTART_NOTE = "Interrupted by a restart while it was running. Pull again."


def _orphans(db: Session, client_id) -> list[SyncJob]:
    """Jobs still marked running that cannot be: the worker has started a later job (of any client, finished or not) and
    this one has been silent for a while. A deploy restarts the worker and leaves its running job like this until the 45-minute stale clear."""
    now = datetime.now(timezone.utc)
    latest_start = db.query(func.max(SyncJob.started_at)).scalar()
    out = []
    for job in db.query(SyncJob).filter(SyncJob.client_id == client_id, SyncJob.status.in_(RUNNING)):
        silent = (now - job.updated_at).total_seconds() / 60 if job.updated_at else 0
        if job.started_at and latest_start and latest_start > job.started_at and silent >= ORPHAN_SILENT_MINUTES:
            out.append(job)
    return out


def _clear_orphans(db: Session, client_id) -> None:
    jobs = _orphans(db, client_id)
    for job in jobs:
        job.status, job.error_message, job.completed_at = SyncJobStatus.FAILED, RESTART_NOTE, datetime.now(timezone.utc)
    if jobs:
        db.commit()


def queue_pull(db: Session, client: Any, today: date | None = None) -> list[str]:
    """Queue one job per planned source. A source that already has an active job is left alone."""
    _clear_orphans(db, client.id)
    queued: list[str] = []
    for item in pull_plan(db, client, today):
        try:
            enqueue_sync_job(db, client.id, SyncJobCreate(source=item["source"], start_date=item["start"], end_date=item["end"]))
            queued.append(item["source"])
        except OverlappingJobError:
            pass
    return queued


def _pull_started(db: Session, client_id) -> datetime | None:
    """When the current pull began: the first job of the newest batch (jobs queued within a minute of each other)."""
    newest = db.query(func.max(SyncJob.created_at)).filter(SyncJob.client_id == client_id).scalar()
    if newest is None:
        return None
    return db.query(func.min(SyncJob.created_at)).filter(SyncJob.client_id == client_id, SyncJob.created_at >= newest - timedelta(minutes=2)).scalar()


def pull_status(db: Session, client: Any, today: date | None = None) -> dict:
    now = datetime.now(timezone.utc)
    plan = pull_plan(db, client, today)
    began = _pull_started(db, client.id)
    jobs: dict[str, SyncJob] = {}
    if began is not None:
        for job in db.query(SyncJob).filter(SyncJob.client_id == client.id, SyncJob.created_at >= began).order_by(SyncJob.created_at):
            jobs[job.source] = job

    # Jobs ahead of ours in the one queue, from every client.
    ahead = db.query(func.count()).select_from(SyncJob).filter(SyncJob.status == SyncJobStatus.QUEUED, SyncJob.client_id != client.id)
    if began is not None:
        ahead = ahead.filter(SyncJob.created_at < began)

    orphan_ids = {j.id for j in _orphans(db, client.id)}
    sources = []
    for item in plan:
        job = jobs.get(item["source"])
        row = {"source": item["source"], "label": item["label"], "reach": item["reach"], "from": item["start"].isoformat(), "to": item["end"].isoformat(),
               "state": "not_started", "stage": None, "running_seconds": None, "error": None, "rows": None}
        if job is not None:
            status = job.status
            row["stage"] = STAGE_TEXT.get(status)
            row["rows"] = job.records_written
            if job.id in orphan_ids:
                row["state"], row["error"], row["stage"] = "failed", RESTART_NOTE, STAGE_TEXT[SyncJobStatus.FAILED]
            elif status in ACTIVE:
                row["state"] = "queued" if status == SyncJobStatus.QUEUED else "running"
                if job.started_at is not None:
                    row["running_seconds"] = int((now - job.started_at).total_seconds())
            elif status == SyncJobStatus.FAILED:
                row["state"], row["error"] = "failed", job.error_message
            else:
                row["state"] = "done" if status == SyncJobStatus.SUCCESSFUL else "partial"
        sources.append(row)

    active = [s for s in sources if s["state"] in ("queued", "running")]
    done = [s for s in sources if s["state"] in ("done", "partial")]
    return {
        "sources": sources,
        "started_at": began.isoformat() if began else None,
        "running": bool(active),
        "finished": bool(sources) and not active and len(done) == len(sources) and began is not None,
        "failed": [s["label"] for s in sources if s["state"] == "failed"],
        "jobs_done": len(done),
        "jobs_total": len(sources),
        "jobs_ahead": ahead.scalar() or 0,
    }
