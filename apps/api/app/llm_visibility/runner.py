"""Run the watchlist's paired prompts against every platform that has a key, and keep what each answered."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.llm_visibility import analyze as analysis
from app.llm_visibility import platforms
from app.models.client import Client
from app.models.job import SyncJob, SyncJobStatus, ValidationStatus
from app.models.llm_visibility import ClientLlmSettings, LlmResponse, LlmRun
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services.competitors import bare_domain

logger = logging.getLogger("organiciq.llm_visibility")

SOURCE = "llm_visibility"
#: Calls in flight at once, per platform.
PER_PLATFORM_CONCURRENCY = 4


class NothingToRun(Exception):
    """No prompts, or no platform with a key."""


def _stem(domain: str) -> str:
    """`mineralfusion.com` -> `mineralfusion`."""
    return bare_domain(domain).rsplit(".", 1)[0]


def default_patterns(name: str, domain: str) -> list[str]:
    seen: dict[str, None] = {}
    for value in (name, _stem(domain), bare_domain(domain)):
        v = " ".join((value or "").lower().split())
        if v:
            seen[v] = None
    return list(seen)


def brand_config(db: Session, client: Client) -> analysis.BrandConfig:
    """How to spot this client and its competitors, from saved patterns where there are any."""
    saved = db.query(ClientLlmSettings).filter(ClientLlmSettings.client_id == client.id).one_or_none()
    name = (saved.brand_name if saved and saved.brand_name else client.client_name).strip()
    patterns = list(saved.brand_patterns) if saved and saved.brand_patterns else default_patterns(name, client.domain)
    overrides = (saved.competitors if saved else None) or {}
    competitors: list[tuple[str, list[str]]] = []
    for domain in client.competitor_domains or []:
        bare = bare_domain(domain)
        override = overrides.get(bare) or {}
        competitors.append(
            (
                override.get("name") or _stem(bare).title(),
                [p.lower() for p in override.get("patterns") or default_patterns(_stem(bare), bare)],
            )
        )
    return analysis.BrandConfig(name, [p.lower() for p in patterns], bare_domain(client.domain), competitors)


def prompts_for(db: Session, client: Client) -> list[dict]:
    """The watchlist keywords that carry a paired AI prompt; the keyword's bucket is the topic cluster."""
    rows = (
        db.query(WatchlistKeyword, WatchlistBucket.name)
        .join(WatchlistBucket, WatchlistBucket.id == WatchlistKeyword.bucket_id)
        .filter(WatchlistKeyword.client_id == client.id)
        .order_by(WatchlistBucket.sort_order, WatchlistBucket.name, WatchlistKeyword.keyword)
        .all()
    )
    out = []
    seen: set[str] = set()
    for keyword, bucket in rows:
        prompt = re.sub(r"\s+", " ", keyword.paired_ai_prompt or "").strip()
        if prompt and prompt.lower() not in seen:
            seen.add(prompt.lower())
            out.append({"prompt": prompt, "keyword": keyword.keyword, "cluster": bucket})
    return out


def _ask_one(platform: str, item: dict, config: analysis.BrandConfig) -> dict:
    """One prompt on one platform, analysed. Never raises: an error becomes an Error row."""
    base = {"platform": platforms.DISPLAY[platform], "query_text": item["prompt"], "keyword": item["keyword"], "topic_cluster": item["cluster"]}
    try:
        answer = platforms.ask(platform, item["prompt"])
        result = analysis.analyze(answer.text, answer.citations, config)
        known = [config.brand_name, *(name for name, _ in config.competitors)]
        return {
            **base,
            "visibility_type": analysis.visibility_type(result),
            "brand_mentioned": result.brand_mentioned,
            "url_cited": result.url_cited,
            "cited_urls": result.cited_urls,
            "position": result.position,
            "sources_count": len(answer.citations),
            "competitors_mentioned": result.competitors_mentioned,
            "all_brands_ordered": result.all_brands_ordered,
            "other_brands_mentioned": analysis.extract_other_brands(answer.text, known),
            "brand_rank": result.brand_rank,
            "total_brands": len(result.all_brands_ordered),
            "full_response": answer.text,
            "tokens_used": answer.input_tokens + answer.output_tokens,
            "estimated_cost_usd": platforms.cost_usd(platform, answer.input_tokens, answer.output_tokens),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {**base, "visibility_type": "Error", "error": str(exc)[:500]}


def run_for_client(db: Session, client: Client, *, triggered_by: str = "scheduler") -> LlmRun:
    items = prompts_for(db, client)
    chosen = platforms.enabled_platforms()
    if not items:
        raise NothingToRun("This client's watchlist has no paired AI prompts.")
    if not chosen:
        raise NothingToRun("No AI platform has an API key on this install.")

    config = brand_config(db, client)
    run = LlmRun(client_id=client.id, platforms=chosen, total_calls=len(items) * len(chosen), triggered_by=triggered_by)
    db.add(run)
    db.commit()
    run_id, client_id = run.id, client.id

    errors = 0
    cost = 0.0
    try:
        # One pool per platform, all running together; results are written here, in one thread and one session.
        pools = {p: ThreadPoolExecutor(max_workers=PER_PLATFORM_CONCURRENCY) for p in chosen}
        try:
            futures = [pools[p].submit(_ask_one, p, item, config) for p in chosen for item in items]
            for future in as_completed(futures):
                row = future.result()
                errors += 1 if row["visibility_type"] == "Error" else 0
                cost += float(row.get("estimated_cost_usd") or 0)
                db.add(LlmResponse(run_id=run_id, client_id=client_id, **row))
                db.commit()
        finally:
            for pool in pools.values():
                pool.shutdown(wait=True)
        status, message = "completed", None
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        status, message = "failed", str(exc)[:500]
        logger.exception("LLM visibility run failed client=%s", client_id)

    run = db.get(LlmRun, run_id)
    run.status, run.error = status, message
    run.total_errors = errors
    run.estimated_cost_usd = round(cost, 4)
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    return run


def run_llm_visibility_job(db: Session, job: SyncJob) -> SyncJob:
    """The worker's entry: run the client's prompts and record the outcome on the job."""
    try:
        client = db.query(Client).filter(Client.id == job.client_id).one()
        job.status = SyncJobStatus.FETCHING
        db.commit()
        run = run_for_client(db, client, triggered_by=(job.params_json or {}).get("triggered_by", "scheduler"))
        job.records_fetched = run.total_calls
        job.records_written = (run.total_calls or 0) - run.total_errors
        job.validation_status = ValidationStatus.PASSED if run.status == "completed" and run.total_errors < (run.total_calls or 1) else ValidationStatus.FAILED
        job.status = SyncJobStatus.SUCCESSFUL if run.status == "completed" and job.validation_status == ValidationStatus.PASSED else SyncJobStatus.PARTIAL
        job.error_message = f"{run.total_calls} calls, {run.total_errors} errors, about ${float(run.estimated_cost_usd or 0):.2f}" + (f"; {run.error}" if run.error else "")
        job.fact_watermark = run.started_at.date()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.get(SyncJob, job.id)
        job.status = SyncJobStatus.FAILED
        job.error_message = str(exc)[:500]
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    return job


def latest_runs(db: Session, client_id: UUID, limit: int = 12) -> list[LlmRun]:
    return (
        db.query(LlmRun)
        .filter(LlmRun.client_id == client_id, LlmRun.status == "completed")
        .order_by(LlmRun.started_at.desc())
        .limit(limit)
        .all()
    )
