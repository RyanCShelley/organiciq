from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.integration import Integration, IntegrationProvider
from app.models.scheduler import SchedulerCheckpoint
from app.schemas import SyncJobCreate
from app.services.jobs import OverlappingJobError, enqueue_sync_job

logger = logging.getLogger("organiciq.daily_sync")

DAILY_CHECKPOINT = "daily_client_sync"

# Job sources per mapped integration provider.
_PROVIDER_SOURCES: dict[IntegrationProvider, tuple[str, ...]] = {
    IntegrationProvider.GSC: ("gsc_pages", "gsc_queries"),
    IntegrationProvider.GA4: ("ga4",),
    IntegrationProvider.SE_RANKING: ("se_ranking_search", "se_ranking_ai", "se_ranking_audit"),
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
    checkpoint = db.get(SchedulerCheckpoint, DAILY_CHECKPOINT)
    if checkpoint is None:
        checkpoint = SchedulerCheckpoint(name=DAILY_CHECKPOINT, last_run_date=None)
        db.add(checkpoint)
        db.flush()

    if checkpoint.last_run_date == today:
        return False

    stats = enqueue_daily_syncs(db)
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
    return True
