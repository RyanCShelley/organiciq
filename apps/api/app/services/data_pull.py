"""Pull a client's data from every connected source, and say where the pull stands.

The plan (what is pulled and how far back) is one function so the button, the queueing and the reset tool agree.
Progress comes from the client's sync jobs. A job reports its stage, not a percentage, so time left is an estimate
from how long past jobs of the same source took on this install; with no history yet it says so instead of guessing.
The worker runs one job at a time, so the time left is the sum of the jobs still ahead, including other clients'
jobs queued before ours.
"""

from __future__ import annotations

import statistics
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
# How far through the work each stage is, as a share of a job's typical length. Honest as a rough guide only.
STAGE_SHARE = {
    SyncJobStatus.QUEUED: 0.0,
    SyncJobStatus.FETCHING: 0.1,
    SyncJobStatus.STAGING: 0.6,
    SyncJobStatus.NORMALIZING: 0.8,
    SyncJobStatus.VALIDATING: 0.95,
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


def queue_pull(db: Session, client: Any, today: date | None = None) -> list[str]:
    """Queue one job per planned source. A source that already has an active job is left alone."""
    queued: list[str] = []
    for item in pull_plan(db, client, today):
        try:
            enqueue_sync_job(db, client.id, SyncJobCreate(source=item["source"], start_date=item["start"], end_date=item["end"]))
            queued.append(item["source"])
        except OverlappingJobError:
            pass
    return queued


def _typical_seconds(db: Session, source: str, days: int) -> float | None:
    """Median time past successful jobs of this source took, preferring ones with a similar window."""
    rows = (
        db.query(SyncJob.started_at, SyncJob.completed_at, SyncJob.start_date, SyncJob.end_date)
        .filter(SyncJob.source == source, SyncJob.status == SyncJobStatus.SUCCESSFUL)
        .filter(SyncJob.started_at.isnot(None), SyncJob.completed_at.isnot(None))
        .order_by(SyncJob.completed_at.desc())
        .limit(40)
        .all()
    )
    spans = [((done - began).total_seconds(), (end - start).days) for began, done, start, end in rows]
    similar = [s for s, d in spans if d >= days * 0.5]
    pool = similar or [s for s, _ in spans]
    return statistics.median(pool) if pool else None


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
    ahead_rows = db.query(SyncJob.source, SyncJob.start_date, SyncJob.end_date).filter(
        SyncJob.status == SyncJobStatus.QUEUED, SyncJob.client_id != client.id
    )
    if began is not None:
        ahead_rows = ahead_rows.filter(SyncJob.created_at < began)
    queue_ahead = ahead_rows.all()

    sources, remaining, unknown, overrun = [], 0.0, False, False
    for item in plan:
        job = jobs.get(item["source"])
        typical = _typical_seconds(db, item["source"], (item["end"] - item["start"]).days)
        row = {"source": item["source"], "label": item["label"], "reach": item["reach"], "from": item["start"].isoformat(), "to": item["end"].isoformat(), "state": "not_started", "stage": None, "seconds_left": None, "error": None, "rows": None, "overrun": False, "usual_seconds": None}
        if job is not None:
            status = job.status
            row["stage"] = STAGE_TEXT.get(status)
            row["rows"] = job.records_written
            if status in ACTIVE:
                row["state"] = "queued" if status == SyncJobStatus.QUEUED else "running"
                if typical is not None:
                    elapsed = (now - job.started_at).total_seconds() if job.started_at else 0.0
                    if status != SyncJobStatus.QUEUED and elapsed > typical:
                        # Past its usual time: say so instead of promising "a minute left" for ever.
                        row["overrun"], row["usual_seconds"] = True, int(typical)
                        overrun = True
                    else:
                        row["seconds_left"] = typical if status == SyncJobStatus.QUEUED else typical - elapsed
                        remaining += row["seconds_left"]
                else:
                    unknown = True
            elif status == SyncJobStatus.FAILED:
                row["state"], row["error"] = "failed", job.error_message
            else:
                row["state"] = "done" if status == SyncJobStatus.SUCCESSFUL else "partial"
        sources.append(row)

    ahead_seconds = 0.0
    for source, start, end in queue_ahead:
        typical = _typical_seconds(db, source, (end - start).days)
        ahead_seconds += typical or 0.0
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
        "overrun": overrun,
        "seconds_left": None if ((unknown or overrun) and active) else int(remaining + ahead_seconds) if active else 0,
        "jobs_ahead": len(queue_ahead),
    }
