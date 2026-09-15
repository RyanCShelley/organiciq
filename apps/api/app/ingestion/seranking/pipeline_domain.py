"""Fetch the organic keywords a domain ranks for (SE Ranking Domain Analysis).

Deliberately **not** part of the daily sync. /domain/keywords is metered at 100
credits per request, so this runs only when someone asks for it — see
`daily_sync._PROVIDER_SOURCES`, which does not list this source.

It writes straight to facts with no staging table: the response is a single
page of at most 1000 rows, so there is nothing to stage and nothing to purge.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.ingestion.seranking.client import list_domain_keywords
from app.models.client import Client
from app.models.integration import Integration, IntegrationProvider
from app.models.job import SyncJob, SyncJobStatus, ValidationStatus
from app.models.seranking import FactSerDomainKeyword

logger = logging.getLogger("organiciq.seranking.domain")

# SE Ranking regional database code. primary_market holds free text, so this
# maps the common cases and falls back rather than failing the job.
_MARKET_TO_SOURCE = {
    "us": "us",
    "usa": "us",
    "united states": "us",
    "uk": "uk",
    "united kingdom": "uk",
    "ca": "ca",
    "canada": "ca",
    "au": "au",
    "australia": "au",
}
DEFAULT_SOURCE = "us"


def resolve_source(client: Client) -> str:
    market = (client.primary_market or "").strip().lower()
    return _MARKET_TO_SOURCE.get(market, DEFAULT_SOURCE)


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _serp_features(value: Any) -> list[str] | None:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.split(",") if part.strip()]
    return None


def _domain_for(client: Client, integration: Integration | None) -> str:
    raw = (client.domain or "").strip()
    if not raw and integration is not None:
        raw = (integration.external_property_id or "").strip()
    return raw.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")


def run_seranking_domain_keywords_job(db: Session, job: SyncJob) -> SyncJob:
    try:
        settings = get_settings()
        api_key = settings.se_ranking_api_key
        if not api_key:
            raise RuntimeError("SE_RANKING_API_KEY is not configured")

        client = db.query(Client).filter(Client.id == job.client_id).one_or_none()
        if client is None:
            raise RuntimeError("Client not found")

        integration = (
            db.query(Integration)
            .filter(
                Integration.client_id == job.client_id,
                Integration.provider == IntegrationProvider.SE_RANKING,
            )
            .one_or_none()
        )

        domain = _domain_for(client, integration)
        if not domain:
            raise RuntimeError("Client has no domain set")

        job.status = SyncJobStatus.FETCHING
        db.commit()

        rows = list_domain_keywords(
            api_key=api_key, domain=domain, source=resolve_source(client)
        )
        job.records_fetched = len(rows)

        job.status = SyncJobStatus.NORMALIZING
        db.commit()

        # Replace wholesale: this is a snapshot of what the domain ranks for
        # now, and a keyword that dropped out should disappear from the view.
        db.query(FactSerDomainKeyword).filter(
            FactSerDomainKeyword.client_id == job.client_id
        ).delete(synchronize_session=False)

        now = datetime.now(timezone.utc)
        seen: set[str] = set()
        written = 0
        for row in rows:
            keyword = str(row.get("keyword") or "").strip()
            if not keyword or keyword in seen:
                continue
            seen.add(keyword)
            db.add(
                FactSerDomainKeyword(
                    client_id=job.client_id,
                    keyword=keyword,
                    position=_decimal(row.get("position")),
                    previous_position=_decimal(row.get("prev_pos")),
                    volume=_decimal(row.get("volume")),
                    difficulty=_decimal(row.get("difficulty")),
                    cpc=_decimal(row.get("cpc")),
                    traffic=_decimal(row.get("traffic")),
                    ranking_url=str(row.get("url")) if row.get("url") else None,
                    serp_features=_serp_features(row.get("serp_features")),
                    fetched_at=now,
                )
            )
            written += 1

        job.records_written = written
        job.validation_status = ValidationStatus.PASSED
        job.status = SyncJobStatus.SUCCESSFUL
        job.completed_at = now
        job.error_message = None
        db.commit()
        logger.info(
            "Domain keywords for %s: fetched=%d written=%d", domain, len(rows), written
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
