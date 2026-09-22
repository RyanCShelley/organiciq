from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.client import Client, ClientStatus
from app.models.integration import Integration, IntegrationProvider
from app.models.job import DataWatermark
from app.models.scheduler import SchedulerCheckpoint
from app.schemas import SyncJobCreate
from app.services.jobs import OverlappingJobError, enqueue_sync_job

logger = logging.getLogger("organiciq.daily_sync")

DAILY_CHECKPOINT = "daily_client_sync"

#: A full crawl per client per week. Weekly rather than monthly because the
#: engine now reads this crawl for technical findings: a page that starts
#: returning 404 should not go unreported for a month. The crawl costs no API
#: credits and no third-party rate limit — 35 clients at roughly five a day,
#: and the largest took 2m26s — so frequency is close to free.
SITE_CRAWL_INTERVAL_DAYS = 7
#: Older than this and the crawl is overdue, running on the next tick regardless
#: of its slot, so a worker outage cannot cost a client its turn.
SITE_CRAWL_STALE_DAYS = 14

# Job sources per mapped integration provider.
_PROVIDER_SOURCES: dict[IntegrationProvider, tuple[str, ...]] = {
    IntegrationProvider.GSC: ("gsc_pages", "gsc_queries"),
    IntegrationProvider.GA4: ("ga4",),
    # se_ranking_audit is deliberately absent: the first-party crawl supplies
    # these facts now, and re-fetching the audit daily cost ~13 requests per
    # client per day for a crawl SE Ranking refreshes far less often. The job
    # stays registered and runnable on demand — it is how we would catch our own
    # crawler regressing.
    IntegrationProvider.SE_RANKING: ("se_ranking_search", "se_ranking_ai"),
}


def _lookback_window(lookback_days: int) -> tuple[date, date]:
    end = date.today()
    start = end - timedelta(days=max(lookback_days, 1) - 1)
    return start, end


def _mapped_sources_by_client(db: Session) -> dict:
    rows = (
        db.query(Integration)
        .filter(Integration.external_property_id.isnot(None))
        .filter(Integration.external_property_id != "")
        .all()
    )
    by_client: dict = {}
    for row in rows:
        sources = _PROVIDER_SOURCES.get(row.provider, ())
        if not sources:
            continue
        by_client.setdefault(row.client_id, set()).update(sources)
    return by_client


def enqueue_daily_syncs(db: Session) -> dict[str, int]:
    """Enqueue overlapping lookback syncs for every client with mapped properties."""
    settings = get_settings()
    start, end = _lookback_window(settings.daily_sync_lookback_days)
    mapped = _mapped_sources_by_client(db)

    enqueued = 0
    skipped = 0
    errors = 0

    for client_id, sources in mapped.items():
        for source in sorted(sources):
            try:
                enqueue_sync_job(
                    db,
                    client_id,
                    SyncJobCreate(source=source, start_date=start, end_date=end),
                )
                enqueued += 1
            except OverlappingJobError:
                skipped += 1
            except Exception:  # noqa: BLE001
                errors += 1
                logger.exception(
                    "Daily sync enqueue failed client=%s source=%s", client_id, source
                )

    return {"enqueued": enqueued, "skipped": skipped, "errors": errors, "clients": len(mapped)}



def _crawl_slot(client_id) -> int:
    """
    The day of the 28-day cycle a client crawls on.

    Derived from the client id so it is stable and evenly spread: every client
    gets its own day, nothing bunches, and no state is needed to remember whose
    turn it is. Crawling all 35 clients on the same morning would be a spike of
    outbound traffic for no reason.
    """
    digest = hashlib.sha256(str(client_id).encode("utf-8")).hexdigest()
    return int(digest, 16) % SITE_CRAWL_INTERVAL_DAYS


def _site_crawl_due(client_id, last_crawl: date | None, today: date) -> bool:
    if last_crawl is None:
        return today.toordinal() % SITE_CRAWL_INTERVAL_DAYS == _crawl_slot(client_id)
    age = (today - last_crawl).days
    if age >= SITE_CRAWL_STALE_DAYS:
        return True
    if age < SITE_CRAWL_INTERVAL_DAYS:
        return False
    return today.toordinal() % SITE_CRAWL_INTERVAL_DAYS == _crawl_slot(client_id)


def enqueue_due_site_crawls(db: Session) -> dict[str, int]:
    """Enqueue a full crawl for every client whose turn has come round."""
    settings = get_settings()
    if not settings.site_crawl_enabled:
        return {"enqueued": 0, "skipped": 0, "errors": 0, "due": 0}

    today = date.today()
    last_by_client = {
        row.client_id: row.fact_through_date
        for row in db.query(DataWatermark).filter(DataWatermark.source == "site_crawl")
    }

    clients = (
        db.query(Client)
        .filter(Client.status == ClientStatus.ACTIVE, Client.domain.isnot(None))
        .all()
    )

    enqueued = skipped = errors = due = 0
    for client in clients:
        if not (client.domain or "").strip():
            continue
        if not _site_crawl_due(client.id, last_by_client.get(client.id), today):
            continue
        due += 1
        try:
            enqueue_sync_job(
                db,
                client.id,
                SyncJobCreate(source="site_crawl", start_date=today, end_date=today),
            )
            enqueued += 1
        except OverlappingJobError:
            skipped += 1
        except Exception:  # noqa: BLE001
            errors += 1
            logger.exception("Site crawl enqueue failed client=%s", client.id)

    return {"enqueued": enqueued, "skipped": skipped, "errors": errors, "due": due}


def maybe_run_daily_sync(db: Session) -> bool:
    """
    If daily sync is due (UTC hour reached and not yet run today), enqueue jobs.

    Returns True when a daily run was attempted.
    """
    settings = get_settings()
    if not settings.daily_sync_enabled:
        return False

    now = datetime.now(timezone.utc)
    if now.hour < settings.daily_sync_hour_utc:
        return False

    today = now.date()
    # Lock the checkpoint row: with more than one worker, an unlocked
    # read-then-write lets two of them both decide the run is due and enqueue
    # the whole cycle twice.
    checkpoint = (
        db.query(SchedulerCheckpoint)
        .filter(SchedulerCheckpoint.name == DAILY_CHECKPOINT)
        .with_for_update()
        .one_or_none()
    )
    if checkpoint is None:
        checkpoint = SchedulerCheckpoint(name=DAILY_CHECKPOINT, last_run_date=None)
        db.add(checkpoint)
        try:
            db.flush()
        except IntegrityError:
            # Another worker created it first; it owns this run.
            db.rollback()
            return False

    if checkpoint.last_run_date == today:
        db.rollback()
        return False

    stats = enqueue_daily_syncs(db)
    crawl_stats = enqueue_due_site_crawls(db)
    checkpoint.last_run_date = today
    checkpoint.updated_at = now
    db.commit()
    window_start, window_end = _lookback_window(settings.daily_sync_lookback_days)
    logger.info(
        "Daily sync enqueued clients=%s enqueued=%s skipped=%s errors=%s window=%s→%s",
        stats["clients"],
        stats["enqueued"],
        stats["skipped"],
        stats["errors"],
        window_start,
        window_end,
    )
    if crawl_stats["due"]:
        logger.info(
            "Site crawls due=%s enqueued=%s skipped=%s errors=%s",
            crawl_stats["due"],
            crawl_stats["enqueued"],
            crawl_stats["skipped"],
            crawl_stats["errors"],
        )
    return True
