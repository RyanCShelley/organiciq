"""Run a first-party crawl and publish it as crawl facts.

Writes under its own crawl source, so it sits alongside SE Ranking's Website
Audit rather than replacing it. Nothing reads these rows yet: the point of the
parallel period is to diff the two before anything is switched over.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ingestion.crawler.fetch import (
    CrawledPage,
    CrawlResult,
    crawl_site,
    page_limit_for,
)
from app.models.client import Client
from app.models.crawl import (
    CRAWL_SOURCE_FIRST_PARTY,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from app.models.job import DataWatermark, SyncJob, SyncJobStatus, ValidationStatus

logger = logging.getLogger("organiciq.crawler")

WATERMARK_SOURCE = "site_crawl"
UPSERT_BATCH_SIZE = 500


def _duplicate_keys(pages: list[CrawledPage], attribute: str) -> set[str]:
    """Values that appear on more than one indexable page."""
    counts = Counter(
        getattr(page.parsed, attribute).strip().lower()
        for page in pages
        if page.parsed is not None and page.indexable and getattr(page.parsed, attribute).strip()
    )
    return {value for value, count in counts.items() if count > 1}


def _snapshot_rows(
    client_id: Any, result: CrawlResult, *, snapshot_date: date
) -> list[dict[str, Any]]:
    duplicate_titles = _duplicate_keys(result.pages, "title")
    duplicate_descriptions = _duplicate_keys(result.pages, "description")

    rows: list[dict[str, Any]] = []
    for page in result.pages:
        parsed = page.parsed
        title = parsed.title if parsed else ""
        description = parsed.description if parsed else ""
        rows.append(
            {
                "client_id": client_id,
                "source": CRAWL_SOURCE_FIRST_PARTY,
                "snapshot_date": snapshot_date,
                "raw_url": page.raw_url,
                "normalized_url": page.normalized_url,
                "indexable": page.indexable,
                "status_code": page.status_code,
                "canonical_url": parsed.canonical_url if parsed else None,
                "inbound_internal_links": page.inbound_internal_links,
                "word_count": parsed.word_count if parsed else 0,
                "in_sitemap": page.in_sitemap,
                # Empty string means "crawled and absent"; null would read as
                # "never looked", which is a different finding.
                "title": title,
                "description": description,
                "title_duplicate": bool(title.strip())
                and title.strip().lower() in duplicate_titles,
                "description_duplicate": bool(description.strip())
                and description.strip().lower() in duplicate_descriptions,
                "robots": parsed.robots if parsed else None,
                "blocked_by_robots": page.blocked_by_robots,
                "redirect_url": page.redirect_url,
                "redirect_count": page.redirect_count,
            }
        )
    return rows


def _schema_rows(client_id: Any, result: CrawlResult, *, snapshot_date: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in result.pages:
        if page.parsed is None:
            continue
        for block in page.parsed.schema_blocks:
            rows.append(
                {
                    "client_id": client_id,
                    "snapshot_date": snapshot_date,
                    "normalized_url": page.normalized_url,
                    "syntax": block.syntax,
                    "schema_type": block.schema_type,
                    "raw": block.raw,
                    "raw_text": block.raw_text,
                    "parse_error": block.parse_error,
                }
            )
    return rows


def _chunked(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def _upsert_watermark(db: Session, client_id: Any, through: date, status: ValidationStatus) -> None:
    row = (
        db.query(DataWatermark)
        .filter(DataWatermark.client_id == client_id, DataWatermark.source == WATERMARK_SOURCE)
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if row is None:
        db.add(
            DataWatermark(
                client_id=client_id,
                source=WATERMARK_SOURCE,
                fact_through_date=through,
                last_successful_sync_at=now if status == ValidationStatus.PASSED else None,
                validation_status=status,
            )
        )
    else:
        row.fact_through_date = through
        row.validation_status = status
        if status == ValidationStatus.PASSED:
            row.last_successful_sync_at = now
    db.commit()


def run_site_crawl_job(db: Session, job: SyncJob) -> SyncJob:
    try:
        client = db.query(Client).filter(Client.id == job.client_id).one_or_none()
        if client is None:
            raise RuntimeError("Client not found")
        if not (client.domain or "").strip():
            raise RuntimeError("Client has no domain set")

        params = job.params_json or {}
        try:
            requested = int(params.get("page_limit") or 0) or None
        except (TypeError, ValueError):
            requested = None
        # The client's setting is the ceiling; a job may ask for less but not
        # more. This is the boundary that actually spends time on someone's site.
        ceiling = page_limit_for(client.crawl_page_limit)
        limit = min(page_limit_for(requested), ceiling) if requested else ceiling

        job.status = SyncJobStatus.FETCHING
        db.commit()

        logger.info("Crawling %s (limit=%d)", client.domain, limit)
        result = asyncio.run(crawl_site(client.domain, page_limit=limit))
        job.records_fetched = len(result.pages)

        if not result.pages:
            raise RuntimeError(f"Crawl of {client.domain} returned no pages")

        job.status = SyncJobStatus.NORMALIZING
        db.commit()

        snapshot_date = date.today()
        rows = _snapshot_rows(job.client_id, result, snapshot_date=snapshot_date)
        # A full replacement per crawl: a page removed from the site has to
        # disappear, or the engine keeps reporting on URLs that no longer exist.
        db.query(FactCrawlPageSnapshot).filter(
            FactCrawlPageSnapshot.client_id == job.client_id,
            FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY,
        ).delete(synchronize_session=False)
        for batch in _chunked(rows, UPSERT_BATCH_SIZE):
            db.execute(insert(FactCrawlPageSnapshot).values(batch))

        # Schema is a full replacement per crawl: a block removed from a page
        # has to disappear, and there is no stable key to upsert a block on.
        db.query(FactCrawlPageSchema).filter(
            FactCrawlPageSchema.client_id == job.client_id
        ).delete(synchronize_session=False)
        schema_rows = _schema_rows(job.client_id, result, snapshot_date=snapshot_date)
        for batch in _chunked(schema_rows, UPSERT_BATCH_SIZE):
            db.execute(insert(FactCrawlPageSchema).values(batch))

        job.records_written = len(rows) + len(schema_rows)
        job.fact_watermark = snapshot_date
        job.validation_status = ValidationStatus.PASSED
        job.status = SyncJobStatus.SUCCESSFUL
        job.completed_at = datetime.now(timezone.utc)
        pages_with_schema = len({row["normalized_url"] for row in schema_rows})
        job.error_message = (
            f"Crawled {len(result.pages)} pages "
            f"({sum(1 for p in result.pages if p.indexable)} indexable), "
            f"{len(schema_rows)} schema blocks on {pages_with_schema} pages"
            + (f"; stopped at the {limit}-page limit" if result.hit_page_limit else "")
        )
        db.commit()

        _upsert_watermark(db, job.client_id, snapshot_date, ValidationStatus.PASSED)
        logger.info(
            "Crawl %s: pages=%d schema_blocks=%d hit_limit=%s",
            client.domain,
            len(result.pages),
            len(schema_rows),
            result.hit_page_limit,
        )
        return job

    except Exception as exc:  # noqa: BLE001 — durable job failure boundary
        job_id = job.id
        message = str(exc)[:2000]
        db.rollback()
        job = db.get(SyncJob, job_id)
        if job is None:
            raise
        job.status = SyncJobStatus.FAILED
        job.validation_status = ValidationStatus.FAILED
        job.error_message = message
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return job
