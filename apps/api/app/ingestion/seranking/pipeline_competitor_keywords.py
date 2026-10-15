"""Fetch the organic keywords the client's named competitors rank for.

Read from DataForSEO Labs (ranked keywords), not SE Ranking. The module keeps
its place under `ingestion/seranking` and its job name so nothing that queues
it, and no stored row, has to change.

Each competitor is one request, billed per request plus per row (about $0.13 for
a full 1,000 rows), so the cost is bounded two ways: at most `MAX_COMPETITORS` competitors a client, named in
client settings, and a competitor is not asked for again until
`COMPETITOR_REFRESH_DAYS` have passed. That is 300 credits a client a month at
most, and nothing when the gap analysis has no crawl to compare against (see
`enqueue_due_competitor_keywords`).

Only the terms a competitor ranks well for are kept. The request already
returns volume and difficulty, so a term found here is never priced again.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.integrations import dataforseo
from app.ingestion.seranking.pipeline_domain import resolve_source
from app.models.client import Client
from app.models.job import SyncJob, SyncJobStatus, ValidationStatus
from app.models.seranking import FactSerCompetitorKeyword
from app.services.competitors import MAX_COMPETITORS, clean_competitor_domains

logger = logging.getLogger("organiciq.seranking.competitor_keywords")

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


def named_competitors(client: Client) -> list[str]:
    """The competitors the team named in client settings, at most `MAX_COMPETITORS`.

    Not taken from SE Ranking's competitor list: that is whoever was added to a
    rank-tracking project, and every one read costs 100 credits. A client that
    names none is not read at all.
    """
    return clean_competitor_domains(
        (client.competitor_domains or [])[:MAX_COMPETITORS], own_domain=client.domain
    )


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
    return [domain for domain in named_competitors(client) if domain not in fresh]


def run_seranking_competitor_keywords_job(db: Session, job: SyncJob) -> SyncJob:
    try:
        if not dataforseo.configured():
            raise RuntimeError(
                "DataForSEO is not configured. Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD."
            )
        client = db.query(Client).filter(Client.id == job.client_id).one()
        today = job.end_date or date.today()

        job.status = SyncJobStatus.FETCHING
        db.commit()
        domains = competitors_to_pull(db, client, today=today)
        source = (job.params_json or {}).get("source") or resolve_source(client)

        fetched = written = 0
        for domain in domains:
            rows = dataforseo.ranked_keywords(domain, source=source, max_position=KEEP_POSITION)
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
