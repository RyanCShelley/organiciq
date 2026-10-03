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
    FactCrawlInternalLink,
    FactCrawlPageIssue,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from app.models.job import DataWatermark, SyncJob, SyncJobStatus, ValidationStatus

logger = logging.getLogger("organiciq.crawler")

WATERMARK_SOURCE = "site_crawl"
UPSERT_BATCH_SIZE = 500
#: A ceiling on edges stored per crawl. A page template with a hundred links on
#: every one of five thousand pages is half a million rows of navigation we have
#: already classified as template and would never query.
MAX_STORED_LINKS = 100_000


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
                "inbound_editorial_links": page.inbound_editorial_links,
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
                # A 200 that says 404. Only meaningful on a page that actually
                # returned a success — on a real 404 it is just the error text.
                "soft_404": bool(
                    parsed
                    and parsed.says_not_found
                    and page.status_code is not None
                    and 200 <= page.status_code < 300
                ),
                "blocked_resources": page.blocked_resources,
                "conversion_elements": parsed.conversion_elements if parsed else None,
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


def _site_issue_rows(
    client_id: Any, result: CrawlResult, *, snapshot_date: date
) -> list[dict[str, Any]]:
    """
    Site-level findings, in the same codes the Decision Engine already reads.

    These were the only thing the SE Ranking audit supplied that the crawl did
    not — every page-level code it returns is already a field on our snapshot.
    The crawler sees all of this while planning the crawl; it simply was not
    recording it.
    """
    codes: list[tuple[str, dict[str, Any]]] = []

    if result.robots_txt_error:
        codes.append(("robots_not_accessible", {"error": result.robots_txt_error}))
    elif not result.robots_txt_found:
        codes.append(("no_robots", {}))
    elif result.robots_disallows_site:
        codes.append(("robots_disallow_crawling", {}))

    if result.sitemap_unreadable:
        # Declared and broken, which is worse than absent: something references it.
        codes.append(("robots_has_errors", {"reason": "sitemap declared but unreadable"}))
    elif not result.sitemap_urls:
        codes.append(("sitemap_missing", {}))

    return [
        {
            "client_id": client_id,
            "source": CRAWL_SOURCE_FIRST_PARTY,
            "snapshot_date": snapshot_date,
            "issue_code": code,
            "normalized_url": None,
            "severity": None,
            "raw": raw,
        }
        for code, raw in codes
    ]


def _link_rows(client_id: Any, result: CrawlResult, *, snapshot_date: date) -> list[dict[str, Any]]:
    """
    The link graph, editorial edges first so the cap never discards the ones
    worth having.
    """
    ordered = sorted(result.links, key=lambda e: e.is_template)
    return [
        {
            "client_id": client_id,
            "source": CRAWL_SOURCE_FIRST_PARTY,
            "snapshot_date": snapshot_date,
            "from_url": edge.from_url,
            "to_url": edge.to_url,
            "anchor_text": edge.anchor or None,
            "in_content": edge.in_content,
            "is_template": edge.is_template,
            "occurrences": edge.occurrences,
        }
        for edge in ordered[:MAX_STORED_LINKS]
    ]


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

        scope_note = f"{client.domain}{client.path_prefix or ''}"
        logger.info("Crawling %s (limit=%d)", scope_note, limit)
        result = asyncio.run(
            crawl_site(
                client.domain,
                page_limit=limit,
                sitemap_url=(client.sitemap_url or "").strip() or None,
                path_prefix=(client.path_prefix or "").strip() or None,
            )
        )
        job.records_fetched = len(result.pages)

        if not result.pages:
            raise RuntimeError(f"Crawl of {client.domain} returned no pages")

        # A crawl that fetched nothing must not replace a good one. robots.txt
        # flipping to Disallow, or the site going down, would otherwise publish
        # every page as status-less and non-indexable — wiping real data and
        # turning one true finding into a page-by-page flood of false ones.
        # The site-level issue is still recorded, so the engine reports the
        # cause at its proper severity.
        fetched = [page for page in result.pages if page.status_code is not None]
        if not fetched:
            blocked = sum(1 for page in result.pages if page.blocked_by_robots)
            reason = (
                "robots.txt disallows crawling"
                if blocked
                else "no page could be fetched"
            )
            db.query(FactCrawlPageIssue).filter(
                FactCrawlPageIssue.client_id == job.client_id,
                FactCrawlPageIssue.source == CRAWL_SOURCE_FIRST_PARTY,
            ).delete(synchronize_session=False)
            issue_rows = _site_issue_rows(job.client_id, result, snapshot_date=date.today())
            if issue_rows:
                db.execute(insert(FactCrawlPageIssue).values(issue_rows))
            job.records_written = len(issue_rows)
            job.validation_status = ValidationStatus.FAILED
            job.status = SyncJobStatus.PARTIAL
            job.completed_at = datetime.now(timezone.utc)
            job.error_message = (
                f"{client.domain}: {reason} — kept the previous crawl rather than "
                f"replacing it with {len(result.pages)} unreadable pages"
            )
            db.commit()
            logger.warning("Crawl of %s blocked: %s", client.domain, reason)
            return job

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

        db.query(FactCrawlInternalLink).filter(
            FactCrawlInternalLink.client_id == job.client_id,
            FactCrawlInternalLink.source == CRAWL_SOURCE_FIRST_PARTY,
        ).delete(synchronize_session=False)
        link_rows = _link_rows(job.client_id, result, snapshot_date=snapshot_date)
        for batch in _chunked(link_rows, UPSERT_BATCH_SIZE):
            db.execute(insert(FactCrawlInternalLink).values(batch))

        db.query(FactCrawlPageIssue).filter(
            FactCrawlPageIssue.client_id == job.client_id,
            FactCrawlPageIssue.source == CRAWL_SOURCE_FIRST_PARTY,
        ).delete(synchronize_session=False)
        issue_rows = _site_issue_rows(job.client_id, result, snapshot_date=snapshot_date)
        if issue_rows:
            db.execute(insert(FactCrawlPageIssue).values(issue_rows))

        job.records_written = len(rows) + len(schema_rows) + len(issue_rows) + len(link_rows)
        job.fact_watermark = snapshot_date
        job.validation_status = ValidationStatus.PASSED
        job.status = SyncJobStatus.SUCCESSFUL
        job.completed_at = datetime.now(timezone.utc)
        pages_with_schema = len({row["normalized_url"] for row in schema_rows})
        if result.sitemap_urls:
            where = result.sitemap_location or "robots.txt"
            sitemap_note = f"sitemap {len(result.sitemap_urls)} URLs via {where}"
        elif result.sitemap_unreadable:
            sitemap_note = "sitemap declared but unreadable"
        else:
            sitemap_note = "no sitemap found"
        job.error_message = (
            f"Crawled {len(result.pages)} pages "
            f"({sum(1 for p in result.pages if p.indexable)} indexable), "
            f"{len(schema_rows)} schema blocks on {pages_with_schema} pages, "
            f"{sum(1 for r in link_rows if not r['is_template'])} editorial links, "
            f"{sitemap_note}"
            + (f"; stopped at the {limit}-page limit" if result.hit_page_limit else "")
        )
        db.commit()

        _upsert_watermark(db, job.client_id, snapshot_date, ValidationStatus.PASSED)
        logger.info(
            "Crawl %s: pages=%d schema_blocks=%d sitemap_urls=%d sitemap_at=%s hit_limit=%s",
            client.domain,
            len(result.pages),
            len(schema_rows),
            len(result.sitemap_urls),
            result.sitemap_location or ("robots.txt" if result.sitemap_urls else "none"),
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
