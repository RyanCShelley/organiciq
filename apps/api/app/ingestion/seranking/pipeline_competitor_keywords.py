"""Fetch the organic keywords the closest competitors rank for.

Each competitor is one /domain/keywords request at 100 credits, so the cost is
bounded two ways: at most `COMPETITOR_LIMIT` competitors a client, and a
competitor is not asked for again until `COMPETITOR_REFRESH_DAYS` have passed.
That is 300 credits a client a month at most, and nothing when the gap
analysis has no crawl to compare against (see `enqueue_due_competitor_keywords`).

Only the terms a competitor ranks well for are kept. The request already
returns volume and difficulty, so a term found here is never priced again.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.ingestion.seranking.client import list_domain_keywords
from app.ingestion.seranking.pipeline_domain import resolve_source
from app.models.client import Client
from app.models.job import SyncJob, SyncJobStatus, ValidationStatus
from app.models.seranking import FactSerCompetitor, FactSerCompetitorKeyword

logger = logging.getLogger("organiciq.seranking.competitor_keywords")

#: Competitors read per client. SE Ranking bills each one 100 credits a request.
COMPETITOR_LIMIT = 3

#: A competitor's rankings move slowly and the gap analysis runs monthly.
COMPETITOR_REFRESH_DAYS = 30

#: Kept only where the competitor ranks this well: below it they are not
#: showing the site what wins, and the rows would only be storage.
KEEP_POSITION = 10


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def bare_domain(value: str | None) -> str:
    text = (value or "").strip().lower()
    if "://" in text:
        text = urlsplit(text).netloc or text
    return text.split("/")[0].removeprefix("www.")


def closest_competitors(db: Session, client: Client) -> list[str]:
    """The `COMPETITOR_LIMIT` competitors with the most search visibility.

    The visibility SE Ranking measures for each competitor against the site's
    own keywords: the highest are the ones taking the searches the site wants.
    """
    own = bare_domain(client.domain)
    latest = (
        db.query(FactSerCompetitor.competitor_id, func.max(FactSerCompetitor.metric_date).label("last_date"))
        .filter(FactSerCompetitor.client_id == client.id)
        .group_by(FactSerCompetitor.competitor_id)
        .subquery()
    )
    rows = (
        db.query(FactSerCompetitor)
        .join(
            latest,
            (FactSerCompetitor.competitor_id == latest.c.competitor_id)
            & (FactSerCompetitor.metric_date == latest.c.last_date),
        )
        .filter(FactSerCompetitor.client_id == client.id)
        .all()
    )
    ranked: dict[str, float] = {}
    for row in rows:
        domain = bare_domain(row.url or row.name)
        if not domain or "." not in domain or domain == own:
            continue
        ranked[domain] = max(ranked.get(domain, -1.0), float(row.visibility or 0))
    ordered = sorted(ranked, key=lambda domain: (-ranked[domain], domain))
    return ordered[:COMPETITOR_LIMIT]


def competitors_to_pull(
    db: Session, client: Client, *, today: date | None = None
) -> list[str]:
    """The closest competitors not read within the refresh interval."""
    today = today or date.today()
    cutoff = today - timedelta(days=COMPETITOR_REFRESH_DAYS)
    fresh = {
        domain
        for (domain,) in db.query(FactSerCompetitorKeyword.competitor_domain)
        .filter(
            FactSerCompetitorKeyword.client_id == client.id,
            FactSerCompetitorKeyword.fetched_at > cutoff,
        )
        .distinct()
    }
    return [domain for domain in closest_competitors(db, client) if domain not in fresh]


def run_seranking_competitor_keywords_job(db: Session, job: SyncJob) -> SyncJob:
    try:
        api_key = get_settings().se_ranking_api_key
        if not api_key:
            raise RuntimeError("SE_RANKING_API_KEY is not configured")
        client = db.query(Client).filter(Client.id == job.client_id).one()
        today = job.end_date or date.today()

        job.status = SyncJobStatus.FETCHING
        db.commit()
        domains = competitors_to_pull(db, client, today=today)
        source = (job.params_json or {}).get("source") or resolve_source(client)

        fetched = written = 0
        for domain in domains:
            rows = list_domain_keywords(api_key=api_key, domain=domain, source=source)
            fetched += len(rows)
            payloads = []
            seen: set[str] = set()
            for row in rows:
                keyword = str(row.get("keyword") or "").strip()
                position = _decimal(row.get("position"))
                if (
                    not keyword
                    or keyword.lower() in seen
                    or position is None
                    or not 0 < position <= KEEP_POSITION
                ):
                    continue
                seen.add(keyword.lower())
                payloads.append(
                    FactSerCompetitorKeyword(
                        id=uuid4(),
                        client_id=client.id,
                        competitor_domain=domain,
                        keyword=keyword[:512],
                        position=position,
                        volume=_decimal(row.get("volume")),
                        difficulty=_decimal(row.get("difficulty")),
                        cpc=_decimal(row.get("cpc")),
                        ranking_url=str(row.get("url")) if row.get("url") else None,
                        fetched_at=today,
                    )
                )
            # A snapshot of what the competitor ranks for now: a term it lost
            # should stop looking like demand it holds. Committed per
            # competitor so a failure on the third keeps the first two.
            db.query(FactSerCompetitorKeyword).filter(
                FactSerCompetitorKeyword.client_id == client.id,
                FactSerCompetitorKeyword.competitor_domain == domain,
            ).delete(synchronize_session=False)
            db.add_all(payloads)
            db.commit()
            written += len(payloads)

        job.records_fetched = fetched
        job.records_written = written
        job.validation_status = ValidationStatus.PASSED if domains else ValidationStatus.SKIPPED
        job.status = SyncJobStatus.SUCCESSFUL
        job.completed_at = datetime.now(timezone.utc)
        job.error_message = None
        db.commit()
        logger.info(
            "Competitor keywords for %s: competitors=%d fetched=%d stored=%d",
            client.domain,
            len(domains),
            fetched,
            written,
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
