"""What a sync job did, and what it left behind.

A job row says "completed"; it does not say whether anything useful landed.
For a source being run for the first time those are different questions, and
only the second one matters.

Read-only.

    python -m app.job_status --client sma-marketing [--source se_ranking_backlinks]
    python -m app.job_status --job <uuid>
"""

from __future__ import annotations

import argparse
import logging
from uuid import UUID

from sqlalchemy import func

from app.core.db import SessionLocal
from app.models.client import Client
from app.models.job import DataWatermark, SyncJob
from app.models.seranking import FactSerBacklinkPage

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("organiciq.job_status")


def _print_job(job: SyncJob) -> None:
    logger.info(
        "  %-24s %-11s  fetched=%s written=%s  %s",
        job.source,
        job.status.value,
        job.records_fetched if job.records_fetched is not None else "-",
        job.records_written if job.records_written is not None else "-",
        job.completed_at.strftime("%H:%M:%S") if job.completed_at else "running",
    )
    if job.error_message:
        logger.info("      error: %s", job.error_message[:400])


def _print_backlinks(db, client: Client) -> None:
    rows = (
        db.query(FactSerBacklinkPage)
        .filter(FactSerBacklinkPage.client_id == client.id)
        .order_by(FactSerBacklinkPage.refdomains.desc())
        .all()
    )
    if not rows:
        logger.info("\nNo backlink rows stored.")
        return

    total_domains = db.query(func.sum(FactSerBacklinkPage.refdomains)).filter(
        FactSerBacklinkPage.client_id == client.id
    ).scalar()
    logger.info(
        "\n%d pages with links, %s referring domains in total, snapshot %s",
        len(rows),
        total_domains,
        rows[0].snapshot_date,
    )
    dated = [row for row in rows if row.first_seen]
    logger.info(
        "  %d pages carry a first_seen date (needed for the PR-push rule)", len(dated)
    )
    logger.info("\n  %-58s %6s %6s %s", "page", "refdom", "links", "first seen")
    for row in rows[:25]:
        logger.info(
            "  %-58s %6d %6d %s",
            row.normalized_url[-58:],
            row.refdomains,
            row.backlinks,
            row.first_seen or "-",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", help="client slug")
    parser.add_argument("--job", help="one job id")
    parser.add_argument("--source", help="filter to one source")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.job:
            job = db.query(SyncJob).filter(SyncJob.id == UUID(args.job)).one_or_none()
            if job is None:
                logger.error("No job %s", args.job)
                return 1
            client = db.query(Client).filter(Client.id == job.client_id).one()
            logger.info("%s", client.client_name)
            _print_job(job)
            if job.source == "se_ranking_backlinks":
                _print_backlinks(db, client)
            return 0

        if not args.client:
            logger.error("Need --client or --job")
            return 1
        client = db.query(Client).filter(Client.slug == args.client).one_or_none()
        if client is None:
            logger.error("No client with slug %r", args.client)
            return 1

        query = db.query(SyncJob).filter(SyncJob.client_id == client.id)
        if args.source:
            query = query.filter(SyncJob.source == args.source)
        jobs = query.order_by(SyncJob.created_at.desc()).limit(args.limit).all()

        logger.info("%s — %d most recent jobs", client.client_name, len(jobs))
        for job in jobs:
            _print_job(job)

        marks = (
            db.query(DataWatermark)
            .filter(DataWatermark.client_id == client.id)
            .order_by(DataWatermark.source)
            .all()
        )
        logger.info("\nWatermarks:")
        for mark in marks:
            logger.info(
                "  %-24s %s  %s",
                mark.source,
                mark.fact_through_date or "-",
                mark.validation_status.value if mark.validation_status else "-",
            )

        if args.source == "se_ranking_backlinks" or any(
            job.source == "se_ranking_backlinks" for job in jobs
        ):
            _print_backlinks(db, client)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
