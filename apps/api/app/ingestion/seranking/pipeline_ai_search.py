"""Discover prompts a brand appears in (SE Ranking AI Search).

Deliberately **not** part of the daily sync, and more strictly bounded than any
other source: prompts-by-target costs 200 credits per returned prompt, so a
careless default is a five-figure spend. The job refuses to run without an
explicit engine, caps the prompt count, and records what it spent.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.ingestion.seranking.client import (
    AI_SEARCH_DEFAULT_LIMIT,
    AI_SEARCH_ENGINES,
    ai_search_credit_cost,
    ai_search_limit_for,
    list_ai_search_prompts_by_target,
)
from app.ingestion.seranking.pipeline_domain import _domain_for, resolve_source
from app.models.client import Client
from app.models.integration import Integration, IntegrationProvider
from app.models.job import SyncJob, SyncJobStatus, ValidationStatus
from app.models.seranking import FactSerAiSearchPrompt

logger = logging.getLogger("organiciq.seranking.ai_search")


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _links(answer: Any) -> list[str] | None:
    if not isinstance(answer, dict):
        return None
    links = answer.get("links")
    if not isinstance(links, list):
        return None
    out: list[str] = []
    for link in links:
        if isinstance(link, str):
            out.append(link)
        elif isinstance(link, dict):
            url = link.get("url") or link.get("link")
            if url:
                out.append(str(url))
    return out or None


def run_seranking_ai_search_job(db: Session, job: SyncJob) -> SyncJob:
    try:
        settings = get_settings()
        api_key = settings.se_ranking_api_key
        if not api_key:
            raise RuntimeError("SE_RANKING_API_KEY is not configured")

        params = job.params_json or {}
        engine = str(params.get("engine") or "").strip()
        if engine not in AI_SEARCH_ENGINES:
            # No silent default: picking an engine costs money, so it must be
            # a deliberate choice rather than something this job assumes.
            raise RuntimeError(
                f"An AI engine must be chosen (one of {', '.join(AI_SEARCH_ENGINES)})"
            )

        client = db.query(Client).filter(Client.id == job.client_id).one_or_none()
        if client is None:
            raise RuntimeError("Client not found")

        try:
            requested = int(params.get("limit") or AI_SEARCH_DEFAULT_LIMIT)
        except (TypeError, ValueError):
            requested = AI_SEARCH_DEFAULT_LIMIT
        # Enforce the client's ceiling here, not only in the UI — this is the
        # boundary that actually spends money.
        ceiling = ai_search_limit_for(client.ai_search_prompt_limit)
        limit = max(1, min(requested, ceiling))

        integration = (
            db.query(Integration)
            .filter(
                Integration.client_id == job.client_id,
                Integration.provider == IntegrationProvider.SE_RANKING,
            )
            .one_or_none()
        )
        target = _domain_for(client, integration)
        if not target:
            raise RuntimeError("Client has no domain set")

        job.status = SyncJobStatus.FETCHING
        db.commit()

        logger.info(
            "AI search: target=%s engine=%s limit=%d (~%d credits)",
            target,
            engine,
            limit,
            ai_search_credit_cost(limit),
        )
        result = list_ai_search_prompts_by_target(
            api_key=api_key,
            target=target,
            engine=engine,
            source=resolve_source(client),
            limit=limit,
        )
        rows = result["prompts"]
        job.records_fetched = len(rows)

        job.status = SyncJobStatus.NORMALIZING
        db.commit()

        # Replace this engine's rows only — other engines were paid for
        # separately and must survive.
        db.query(FactSerAiSearchPrompt).filter(
            FactSerAiSearchPrompt.client_id == job.client_id,
            FactSerAiSearchPrompt.engine == engine,
        ).delete(synchronize_session=False)

        snapshot = None
        if result.get("date"):
            try:
                snapshot = date.fromisoformat(str(result["date"]))
            except ValueError:
                snapshot = None

        now = datetime.now(timezone.utc)
        seen: set[str] = set()
        written = 0
        for row in rows:
            prompt = str(row.get("prompt") or "").strip()
            if not prompt or prompt in seen:
                continue
            seen.add(prompt)
            db.add(
                FactSerAiSearchPrompt(
                    client_id=job.client_id,
                    engine=engine,
                    prompt=prompt,
                    volume=_decimal(row.get("volume")),
                    appearance_type=str(row.get("type")) if row.get("type") else None,
                    answer_links=_links(row.get("answer")),
                    snapshot_date=snapshot,
                    fetched_at=now,
                )
            )
            written += 1

        job.records_written = written
        job.validation_status = ValidationStatus.PASSED
        job.status = SyncJobStatus.SUCCESSFUL
        job.completed_at = now
        job.error_message = None
        # Record the spend on the job so cost is auditable after the fact.
        job.params_json = {
            **params,
            "engine": engine,
            "limit": limit,
            "credits_spent_estimate": ai_search_credit_cost(len(rows)),
        }
        db.commit()
        logger.info(
            "AI search %s/%s: fetched=%d written=%d", target, engine, len(rows), written
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
