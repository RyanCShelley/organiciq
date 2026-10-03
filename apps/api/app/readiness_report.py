"""Which clients the Decision Engine can run for, and what is missing.

The engine needs four sources before it will say anything. When it refuses,
the dashboard says so one client at a time, which makes it hard to tell a
client nobody has finished setting up from a client whose ingestion is
broken. This reads all of them at once.

    python -m app.readiness_report
    python -m app.readiness_report --queue site_crawl   # and fix one of them

Queueing skips any client that already has an active job for that source.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from app.core.db import SessionLocal
from app.models.client import Client, ClientStatus
from app.models.job import SyncJob, SyncJobStatus
from app.schemas import SyncJobCreate
from app.services.jobs import OverlappingJobError, enqueue_sync_job
from app.services.lever_engine import diagnose

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("organiciq.readiness")

ACTIVE = (
    SyncJobStatus.QUEUED,
    SyncJobStatus.FETCHING,
    SyncJobStatus.STAGING,
    SyncJobStatus.NORMALIZING,
    SyncJobStatus.VALIDATING,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--queue", help="queue this source for every client missing it")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        clients = (
            db.query(Client)
            .filter(Client.status != ClientStatus.ARCHIVED)
            .order_by(Client.client_name)
            .all()
        )
        end = date.today()
        start = end - timedelta(days=args.days - 1)

        ready: list[str] = []
        blocked: list[tuple[str, list[str]]] = []

        for client in clients:
            result = diagnose(db, client, from_date=start, to_date=end)
            missing = sorted(
                name for name, ok in (result.readiness or {}).items() if not ok
            )
            if result.ready:
                ready.append(f"{client.client_name} ({len(result.findings)} findings)")
            else:
                blocked.append((client.client_name, missing))

        logger.info("%d clients\n", len(clients))
        logger.info("READY (%d):", len(ready))
        for line in ready:
            logger.info("  %s", line)

        logger.info("\nBLOCKED (%d):", len(blocked))
        for name, missing in blocked:
            logger.info("  %-34s missing %s", name[:34], ", ".join(missing) or "?")

        if not args.queue:
            return 0

        logger.info("\nQueueing %s:", args.queue)
        queued = skipped = 0
        for client in clients:
            active = (
                db.query(SyncJob)
                .filter(
                    SyncJob.client_id == client.id,
                    SyncJob.source == args.queue,
                    SyncJob.status.in_(ACTIVE),
                )
                .first()
            )
            if active is not None:
                logger.info("  %-34s already running", client.client_name[:34])
                skipped += 1
                continue
            try:
                enqueue_sync_job(
                    db,
                    client.id,
                    SyncJobCreate(source=args.queue, start_date=end, end_date=end),
                )
                logger.info("  %-34s queued", client.client_name[:34])
                queued += 1
            except (OverlappingJobError, ValueError) as exc:
                logger.info("  %-34s %s", client.client_name[:34], exc)
                skipped += 1
        logger.info("\n%d queued, %d skipped", queued, skipped)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
