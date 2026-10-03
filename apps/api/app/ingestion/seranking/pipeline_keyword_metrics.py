"""Market data for the keywords a client tracks, ranked or not.

Every "nothing ranks for this" finding is an estimate of what winning the
term would be worth, and that estimate was being made with no idea how hard
the term is. On smamarketing.com it valued "seo services" at sixty leads a
period for a site earning fourteen.

Difficulty is the missing input. The rank tracker does not carry it and the
domain-keywords endpoint only covers terms already ranking, so this asks
the keyword database directly.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.ingestion.seranking.client import fetch_keyword_metrics
from app.models.client import Client
from app.models.job import SyncJob, SyncJobStatus, ValidationStatus
from app.models.seranking import FactSerKeyword, FactSerKeywordMetric

logger = logging.getLogger(__name__)


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def tracked_keywords(db: Session, client_id) -> list[str]:
    rows = (
        db.query(FactSerKeyword.keyword)
        .filter(FactSerKeyword.client_id == client_id)
        .distinct()
        .all()
    )
    return [row[0].strip() for row in rows if row[0] and row[0].strip()]


def run_seranking_keyword_metrics_job(db: Session, job: SyncJob) -> SyncJob:
    try:
        api_key = get_settings().se_ranking_api_key
        if not api_key:
            raise RuntimeError("SE_RANKING_API_KEY is not configured")
        client = db.query(Client).filter(Client.id == job.client_id).one()

        keywords = tracked_keywords(db, job.client_id)
        job.status = SyncJobStatus.FETCHING
        db.commit()
        if not keywords:
            # Nothing tracked is not a failure; it is a client whose
            # watchlist has not been set up, and billing a lookup for an
            # empty list would be worse than saying so.
            job.records_fetched = 0
            job.records_written = 0
            job.validation_status = ValidationStatus.SKIPPED
            job.status = SyncJobStatus.SUCCESSFUL
            job.completed_at = datetime.now(timezone.utc)
            job.error_message = None
            db.commit()
            return job

        source = (job.params_json or {}).get("source") or "us"
        rows = fetch_keyword_metrics(api_key, keywords, source=source)
        job.records_fetched = len(rows)

        today = job.end_date or date.today()
        payloads = []
        seen: set[str] = set()
        for row in rows:
            keyword = str(row.get("keyword") or "").strip()
            if not keyword or keyword.lower() in seen:
                continue
            seen.add(keyword.lower())
            payloads.append(
                {
                    "id": uuid4(),
                    "client_id": job.client_id,
                    "keyword": keyword,
                    "source": source,
                    "volume": _decimal(row.get("volume")),
                    "difficulty": _decimal(row.get("difficulty")),
                    "cpc": _decimal(row.get("cpc")),
                    "competition": _decimal(row.get("competition")),
                    "intents": row.get("intents") if isinstance(row.get("intents"), list) else None,
                    "data_found": bool(row.get("is_data_found", True)),
                    "fetched_at": today,
                }
            )

        if payloads:
            stmt = insert(FactSerKeywordMetric).values(payloads)
            db.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_ser_keyword_metrics_grain",
                    set_={
                        "volume": stmt.excluded.volume,
                        "difficulty": stmt.excluded.difficulty,
                        "cpc": stmt.excluded.cpc,
                        "competition": stmt.excluded.competition,
                        "intents": stmt.excluded.intents,
                        "data_found": stmt.excluded.data_found,
                        "fetched_at": stmt.excluded.fetched_at,
                    },
                )
            )

        job.records_written = len(payloads)
        job.validation_status = ValidationStatus.PASSED
        job.status = SyncJobStatus.SUCCESSFUL
        job.completed_at = datetime.now(timezone.utc)
        job.error_message = None
        db.commit()
        logger.info(
            "Keyword metrics for %s: asked %d, stored %d",
            client.domain,
            len(keywords),
            len(payloads),
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
