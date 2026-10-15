"""Market data for the keywords a client tracks, ranked or not.

Every "nothing ranks for this" finding is an estimate of what winning the
term would be worth, and that estimate was being made with no idea how hard
the term is. On smamarketing.com it valued "seo services" at sixty leads a
period for a site earning fourteen.

Difficulty is the missing input. The rank tracker does not carry it and the
domain-keywords endpoint only covers terms already ranking, so this asks
the keyword database directly.

The keyword database is DataForSEO Labs (keyword overview). The module keeps
its name and its job source so nothing that queues it has to change. Rows
bought earlier from SE Ranking stay until they are older than the refresh
interval and are priced again; for that month the two vendors' difficulty
figures sit side by side on slightly different scales.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.integrations import dataforseo
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


#: How long a keyword's market data is treated as current. SE Ranking bills per
#: keyword looked up, and volume and difficulty move slowly.
KEYWORD_METRICS_INTERVAL_DAYS = 30


def keywords_to_price(
    db: Session,
    client_id,
    *,
    today: date | None = None,
    interval_days: int = KEYWORD_METRICS_INTERVAL_DAYS,
) -> list[str]:
    """The tracked terms that actually need a lookup: unpriced, or priced long ago.

    A term already priced is a term already paid for. The job used to send the
    whole tracked list whenever any one term was missing, so adding a keyword
    re-bought every other one, and the "is it due" check compared raw strings,
    so a case or whitespace difference could keep a client due indefinitely.
    Terms are matched on lowercase, trimmed text, and a term SE Ranking had no
    data for counts as priced: that was an answer, and asking again is the same
    cost for the same answer.
    """
    today = today or date.today()
    cutoff = today - timedelta(days=interval_days)
    fresh = {
        (keyword or "").strip().lower()
        for (keyword,) in db.query(FactSerKeywordMetric.keyword).filter(
            FactSerKeywordMetric.client_id == client_id,
            FactSerKeywordMetric.fetched_at > cutoff,
        )
    }
    seen: set[str] = set()
    out: list[str] = []
    for keyword in tracked_keywords(db, client_id):
        key = keyword.lower()
        if key in fresh or key in seen:
            continue
        seen.add(key)
        out.append(keyword)

    # Search Console demand the site has no page for, which nobody tracks and
    # so nobody has priced. Bought for the few largest only; the gap analysis
    # cannot prescribe a page without a volume and a difficulty.
    from app.models.client import Client
    from app.services.demand_gaps import queries_to_price

    client = db.get(Client, client_id)
    if client is not None:
        for query in queries_to_price(db, client, today=today):
            if query not in seen:
                seen.add(query)
                out.append(query)
    return out


def run_seranking_keyword_metrics_job(db: Session, job: SyncJob) -> SyncJob:
    try:
        if not dataforseo.configured():
            raise RuntimeError(
                "DataForSEO is not configured. Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD."
            )
        client = db.query(Client).filter(Client.id == job.client_id).one()

        # Only what is missing or stale. `refresh_all` is for somebody who
        # means to pay for the whole list again, and nothing sets it by default.
        if (job.params_json or {}).get("refresh_all"):
            keywords = tracked_keywords(db, job.client_id)
        else:
            keywords = keywords_to_price(db, job.client_id, today=job.end_date or date.today())
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
        rows = dataforseo.keyword_overview(keywords, source=source)
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
