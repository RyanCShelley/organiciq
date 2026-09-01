from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ingestion.seranking.engines import brand_cited, brand_mentioned
from app.models.job import SyncJob
from app.models.seranking import (
    FactSerAiCheck,
    FactSerAiPrompt,
    FactSerAiTrackerStats,
    StagingSerAiCheck,
    StagingSerAiPrompt,
    StagingSerAiTrackerStats,
)

UPSERT_BATCH_SIZE = 1000


def _chunked(items: Sequence[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _position_change(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous is None:
        return None
    return previous - current


def publish_seranking_ai(db: Session, job: SyncJob) -> tuple[int, int]:
    prompts = (
        db.query(StagingSerAiPrompt)
        .filter(StagingSerAiPrompt.job_id == job.id, StagingSerAiPrompt.client_id == job.client_id)
        .all()
    )
    checks = (
        db.query(StagingSerAiCheck)
        .filter(StagingSerAiCheck.job_id == job.id, StagingSerAiCheck.client_id == job.client_id)
        .all()
    )

    latest: dict[tuple[str, str], StagingSerAiCheck] = {}
    previous: dict[tuple[str, str], StagingSerAiCheck] = {}
    for row in sorted(checks, key=lambda r: (r.date or job.start_date)):
        if not row.llm_id or not row.prompt_id or row.date is None:
            continue
        key = (row.llm_id, row.prompt_id)
        if key in latest:
            previous[key] = latest[key]
        latest[key] = row

    prompt_meta: dict[tuple[str, str], StagingSerAiPrompt] = {}
    for row in prompts:
        if not row.llm_id or not row.prompt_id or not row.prompt or not row.prompt.strip():
            continue
        prompt_meta[(row.llm_id, row.prompt_id)] = row

    prompt_payloads: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    for key, check in latest.items():
        llm_id, prompt_id = key
        meta = prompt_meta.get(key)
        prompt_text = (meta.prompt if meta else None) or check.prompt
        if not prompt_text or not prompt_text.strip():
            continue
        prev = previous.get(key)
        url_pos = check.url_position
        mention_pos = check.mention_position
        prev_url = prev.url_position if prev else None
        prev_mention = prev.mention_position if prev else None
        if prev_url is None and url_pos is not None and prev is not None:
            prev_url = url_pos
        if prev_mention is None and mention_pos is not None and prev is not None:
            prev_mention = mention_pos
        prompt_payloads.append(
            {
                "client_id": job.client_id,
                "llm_id": llm_id,
                "prompt_id": prompt_id,
                "prompt_llm_id": meta.prompt_llm_id if meta else None,
                "engine": meta.engine if meta and meta.engine else "unknown",
                "prompt": prompt_text.strip(),
                "group_id": meta.group_id if meta else None,
                "group_name": meta.group_name if meta else None,
                "search_volume": meta.search_volume if meta else None,
                "search_intent": meta.search_intent if meta else None,
                "url_position": url_pos,
                "mention_position": mention_pos,
                "url_position_change": _position_change(url_pos, prev_url),
                "mention_position_change": _position_change(mention_pos, prev_mention),
                "brand_mentioned": brand_mentioned(_as_int(mention_pos)),
                "brand_cited": brand_cited(_as_int(url_pos)),
                "citation_url": None,
                "ai_visibility": None,
                "ai_sov": None,
                "checked_at": check.date,
            }
        )
        seen_keys.add(key)

    for key, meta in prompt_meta.items():
        if key in seen_keys:
            continue
        llm_id, prompt_id = key
        prompt_payloads.append(
            {
                "client_id": job.client_id,
                "llm_id": llm_id,
                "prompt_id": prompt_id,
                "prompt_llm_id": meta.prompt_llm_id,
                "engine": meta.engine or "unknown",
                "prompt": meta.prompt.strip(),
                "group_id": meta.group_id,
                "group_name": meta.group_name,
                "search_volume": meta.search_volume,
                "search_intent": meta.search_intent,
                "url_position": None,
                "mention_position": None,
                "url_position_change": None,
                "mention_position_change": None,
                "brand_mentioned": None,
                "brand_cited": None,
                "citation_url": None,
                "ai_visibility": None,
                "ai_sov": None,
                "checked_at": None,
            }
        )

    check_payloads: list[dict[str, Any]] = []
    for row in checks:
        if row.date is None or not row.llm_id or not row.prompt_id:
            continue
        prompt_text = row.prompt
        if not prompt_text:
            meta = prompt_meta.get((row.llm_id, row.prompt_id))
            prompt_text = meta.prompt if meta else None
        if not prompt_text or not prompt_text.strip():
            continue
        check_payloads.append(
            {
                "client_id": job.client_id,
                "date": row.date,
                "llm_id": row.llm_id,
                "prompt_id": row.prompt_id,
                "prompt": prompt_text.strip(),
                "url_position": row.url_position,
                "mention_position": row.mention_position,
                "urls_count": row.urls_count,
                "mentions_count": row.mentions_count,
                "organic_overlap_percent": row.organic_overlap_percent,
                "brand_mentioned": brand_mentioned(_as_int(row.mention_position)),
                "brand_cited": brand_cited(_as_int(row.url_position)),
            }
        )

    for batch in _chunked(prompt_payloads, UPSERT_BATCH_SIZE):
        if not batch:
            continue
        stmt = insert(FactSerAiPrompt).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_facts_ser_ai_prompts_grain",
            set_={
                "prompt_llm_id": stmt.excluded.prompt_llm_id,
                "engine": stmt.excluded.engine,
                "prompt": stmt.excluded.prompt,
                "group_id": stmt.excluded.group_id,
                "group_name": stmt.excluded.group_name,
                "search_volume": stmt.excluded.search_volume,
                "search_intent": stmt.excluded.search_intent,
                "url_position": stmt.excluded.url_position,
                "mention_position": stmt.excluded.mention_position,
                "url_position_change": stmt.excluded.url_position_change,
                "mention_position_change": stmt.excluded.mention_position_change,
                "brand_mentioned": stmt.excluded.brand_mentioned,
                "brand_cited": stmt.excluded.brand_cited,
                "citation_url": stmt.excluded.citation_url,
                "ai_visibility": stmt.excluded.ai_visibility,
                "ai_sov": stmt.excluded.ai_sov,
                "checked_at": stmt.excluded.checked_at,
            },
        )
        db.execute(stmt)

    for batch in _chunked(check_payloads, UPSERT_BATCH_SIZE):
        if not batch:
            continue
        stmt = insert(FactSerAiCheck).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_facts_ser_ai_checks_grain",
            set_={
                "prompt": stmt.excluded.prompt,
                "url_position": stmt.excluded.url_position,
                "mention_position": stmt.excluded.mention_position,
                "urls_count": stmt.excluded.urls_count,
                "mentions_count": stmt.excluded.mentions_count,
                "organic_overlap_percent": stmt.excluded.organic_overlap_percent,
                "brand_mentioned": stmt.excluded.brand_mentioned,
                "brand_cited": stmt.excluded.brand_cited,
            },
        )
        db.execute(stmt)

    db.commit()
    return len(prompt_payloads), len(check_payloads)


def publish_seranking_ai_tracker_stats(db: Session, job: SyncJob) -> int:
    rows = (
        db.query(StagingSerAiTrackerStats)
        .filter(
            StagingSerAiTrackerStats.job_id == job.id,
            StagingSerAiTrackerStats.client_id == job.client_id,
        )
        .all()
    )
    payloads: list[dict[str, Any]] = []
    for row in rows:
        if row.metric_date is None:
            continue
        payloads.append(
            {
                "client_id": job.client_id,
                "metric_date": row.metric_date,
                "prompts_count": row.prompts_count,
                "mention_presence_pct": row.mention_presence_pct,
                "link_presence_pct": row.link_presence_pct,
                "mention_top3_pct": row.mention_top3_pct,
                "link_top3_pct": row.link_top3_pct,
            }
        )

    for batch in _chunked(payloads, UPSERT_BATCH_SIZE):
        if not batch:
            continue
        stmt = insert(FactSerAiTrackerStats).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_facts_ser_ai_tracker_stats_grain",
            set_={
                "prompts_count": stmt.excluded.prompts_count,
                "mention_presence_pct": stmt.excluded.mention_presence_pct,
                "link_presence_pct": stmt.excluded.link_presence_pct,
                "mention_top3_pct": stmt.excluded.mention_top3_pct,
                "link_top3_pct": stmt.excluded.link_top3_pct,
            },
        )
        db.execute(stmt)

    db.commit()
    return len(payloads)


def _as_int(value: Decimal | None) -> int | None:
    if value is None:
        return None
    return int(value)
