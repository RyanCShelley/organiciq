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
from app.services.jobs import lane_of
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
    "dataforseo_competitor_keywords": "Competitor rankings",
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
    # The competitors named in settings: their rankings are bought once a month per competitor, so pulling again within the
    # month reads nothing new and costs nothing.
    from app.ingestion.dataforseo.competitor_keywords import named_competitors
    from app.integrations import dataforseo

    if dataforseo.configured() and named_competitors(client):
        plan.append({"source": "dataforseo_competitor_keywords", "start": today, "end": today, "reach": "what the competitors named in settings rank for (read monthly)"})
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
    # Jobs run one at a time per lane, so "a later job started" only proves anything about jobs in the same lane.
    latest_start: dict[str, datetime] = {}
    for source, started in db.query(SyncJob.source, func.max(SyncJob.started_at)).group_by(SyncJob.source):
        lane = lane_of(source)
        if started is not None and (lane not in latest_start or started > latest_start[lane]):
            latest_start[lane] = started
    out = []
    for job in db.query(SyncJob).filter(SyncJob.client_id == client_id, SyncJob.status.in_(RUNNING)):
        silent = (now - job.updated_at).total_seconds() / 60 if job.updated_at else 0
        later = latest_start.get(lane_of(job.source))
        if job.started_at and later and later > job.started_at and silent >= ORPHAN_SILENT_MINUTES:
            out.append(job)
    return out


def _clear_orphans(db: Session, client_id) -> None:
    jobs = _orphans(db, client_id)
    for job in jobs:
        job.status, job.error_message, job.completed_at = SyncJobStatus.FAILED, RESTART_NOTE, datetime.now(timezone.utc)
    if jobs:
        db.commit()


FRESH_HOURS = 24


def _latest_jobs(db: Session, client_id) -> dict[str, SyncJob]:
    """This client's newest job per source."""
    latest: dict[str, SyncJob] = {}
    for job in db.query(SyncJob).filter(SyncJob.client_id == client_id).order_by(SyncJob.created_at):
        latest[job.source] = job
    return latest


def stop_pull(db: Session, client: Any, who: str) -> dict[str, int]:
    """Stop this client's pull. Jobs still waiting are cancelled now; a running one is asked to stop and does at its next
    page, batch or call (within seconds while fetching; after the save, if it is already saving rows)."""
    sources = {item["source"] for item in pull_plan(db, client)}
    cancelled = asked = 0
    now = datetime.now(timezone.utc)
    for job in db.query(SyncJob).filter(SyncJob.client_id == client.id, SyncJob.source.in_(sources), SyncJob.status.in_(ACTIVE)):
        if job.status == SyncJobStatus.QUEUED:
            job.status, job.completed_at, job.error_message = SyncJobStatus.FAILED, now, f"Stopped by {who} before it started."
            cancelled += 1
        elif not (job.params_json or {}).get("stop_requested_by"):
            job.params_json = {**(job.params_json or {}), "stop_requested_by": who}
            asked += 1
    db.commit()
    return {"cancelled": cancelled, "asked_to_stop": asked}


def set_lean_pull(db: Session, client: Any, enabled: bool) -> list[str]:
    """Switch the client's Search Console pull between lean and full, at once. The two store different rows, so the pull
    queued here replaces the whole window (`replace_gsc_window`): the old rows are removed inside the save, after the new
    ones have arrived, so nothing is cleared up front and the screen is never empty. The daily totals are the same either way."""
    if bool(client.gsc_lean_pull) == enabled:
        return []
    client.gsc_lean_pull = enabled
    db.commit()
    return queue_pull(db, client, force=True, only={"gsc_pages", "gsc_queries"}, params={"replace_gsc_window": True})


def _is_current(job: SyncJob | None, item: dict, now: datetime) -> bool:
    """Already pulled: the newest job finished, within the last day, and reached back as far as this pull would."""
    if job is None or job.status not in (SyncJobStatus.SUCCESSFUL, SyncJobStatus.PARTIAL) or job.completed_at is None:
        return False
    if (now - job.completed_at).total_seconds() > FRESH_HOURS * 3600:
        return False
    return job.start_date <= item["start"] + timedelta(days=3)


def queue_pull(db: Session, client: Any, today: date | None = None, force: bool = False, only: set[str] | None = None, params: dict | None = None) -> list[str]:
    """Queue a job for each planned source that is missing: never pulled, failed, interrupted or older than a day.
    A source already pulling, or already pulled today, is left alone unless force is set. `only` limits it to those sources."""
    _clear_orphans(db, client.id)
    now = datetime.now(timezone.utc)
    latest = _latest_jobs(db, client.id)
    queued: list[str] = []
    for item in pull_plan(db, client, today):
        if only is not None and item["source"] not in only:
            continue
        if not force and _is_current(latest.get(item["source"]), item, now):
            continue
        try:
            enqueue_sync_job(db, client.id, SyncJobCreate(source=item["source"], start_date=item["start"], end_date=item["end"], params=params))
            queued.append(item["source"])
        except OverlappingJobError:
            pass
    return queued


def pull_status(db: Session, client: Any, today: date | None = None) -> dict:
    now = datetime.now(timezone.utc)
    plan = pull_plan(db, client, today)
    jobs = _latest_jobs(db, client.id)
    orphan_ids = {j.id for j in _orphans(db, client.id)}

    # Jobs for other clients queued before ours: they run first, in the one queue.
    mine = [j for j in jobs.values() if j.status == SyncJobStatus.QUEUED]
    ahead = 0
    if mine:
        first = min(mine, key=lambda j: j.created_at)
        ahead = sum(
            1
            for source, in db.query(SyncJob.source).filter(
                SyncJob.status == SyncJobStatus.QUEUED, SyncJob.client_id != client.id, SyncJob.created_at < first.created_at
            )
            if lane_of(source) == lane_of(first.source)
        )

    sources = []
    for item in plan:
        job = jobs.get(item["source"])
        row = {"source": item["source"], "label": item["label"], "reach": item["reach"], "from": item["start"].isoformat(), "to": item["end"].isoformat(),
               "state": "not_started", "stage": None, "running_seconds": None, "error": None, "rows": None, "finished_at": None, "current": False}
        if job is not None:
            status = job.status
            row["stage"] = STAGE_TEXT.get(status)
            row["rows"] = job.records_written
            if job.id in orphan_ids:
                row["state"], row["error"], row["stage"] = "failed", RESTART_NOTE, STAGE_TEXT[SyncJobStatus.FAILED]
            elif status in ACTIVE:
                row["state"] = "queued" if status == SyncJobStatus.QUEUED else "stopping" if (job.params_json or {}).get("stop_requested_by") else "running"
                if job.started_at is not None:
                    row["running_seconds"] = int((now - job.started_at).total_seconds())
            elif status == SyncJobStatus.FAILED:
                stopped = (job.error_message or "").startswith("Stopped by")
                row["state"], row["error"] = ("stopped" if stopped else "failed"), job.error_message
            else:
                row["state"] = "done" if status == SyncJobStatus.SUCCESSFUL else "partial"
                row["finished_at"] = job.completed_at.isoformat() if job.completed_at else None
            row["current"] = _is_current(job, item, now)
        sources.append(row)

    active = [s for s in sources if s["state"] in ("queued", "running", "stopping")]
    done = [s for s in sources if s["state"] in ("done", "partial")]
    return {
        "sources": sources,
        "running": bool(active),
        "finished": bool(sources) and not active and len(done) == len(sources),
        "up_to_date": bool(sources) and all(s["current"] for s in sources),
        "failed": [s["label"] for s in sources if s["state"] == "failed"],
        "stopping": any(s["state"] == "stopping" for s in sources),
        "jobs_done": len(done),
        "jobs_total": len(sources),
        "jobs_ahead": ahead,
    }
