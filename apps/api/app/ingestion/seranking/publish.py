from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ingestion.seranking.features import merge_earned_serp_features
from app.models.job import SyncJob
from app.models.seranking import (
    FactSerCompetitor,
    FactSerKeyword,
    FactSerRanking,
    FactSerSiteSummary,
    StagingSerCompetitor,
    StagingSerKeyword,
    StagingSerPosition,
    StagingSerSiteSummary,
)

UPSERT_BATCH_SIZE = 1000


def _chunked(items: Sequence[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def publish_seranking_search(db: Session, job: SyncJob) -> tuple[int, int, int, int]:
    keywords = (
        db.query(StagingSerKeyword)
        .filter(StagingSerKeyword.job_id == job.id, StagingSerKeyword.client_id == job.client_id)
        .all()
    )
    positions = (
        db.query(StagingSerPosition)
        .filter(StagingSerPosition.job_id == job.id, StagingSerPosition.client_id == job.client_id)
        .all()
    )
    competitors = (
        db.query(StagingSerCompetitor)
        .filter(StagingSerCompetitor.job_id == job.id, StagingSerCompetitor.client_id == job.client_id)
        .all()
    )
    summaries = (
        db.query(StagingSerSiteSummary)
        .filter(StagingSerSiteSummary.job_id == job.id, StagingSerSiteSummary.client_id == job.client_id)
        .all()
    )

    # Latest position per keyword/engine for Watch List snapshot.
    latest: dict[tuple[str, str], StagingSerPosition] = {}
    previous: dict[tuple[str, str], StagingSerPosition] = {}
    for row in sorted(positions, key=lambda r: (r.date or job.start_date)):
        if not row.keyword_id or not row.site_engine_id or row.date is None:
            continue
        key = (row.site_engine_id, row.keyword_id)
        if key in latest:
            previous[key] = latest[key]
        latest[key] = row

    keyword_meta: dict[tuple[str, str], StagingSerKeyword] = {}
    for row in keywords:
        if not row.keyword_id or not row.keyword or not row.keyword.strip():
            continue
        engine = row.site_engine_id or ""
        keyword_meta[(engine, row.keyword_id)] = row

    keyword_payloads: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    for key, pos in latest.items():
        engine_id, keyword_id = key
        meta = keyword_meta.get(key)
        keyword_text = (meta.keyword if meta else None) or pos.keyword
        if not keyword_text or not keyword_text.strip():
            continue
        prev = previous.get(key)
        prev_pos = prev.position if prev else None
        if prev_pos is None and pos.position_change is not None and pos.position is not None:
            prev_pos = pos.position - pos.position_change
        earned_serp_features = merge_earned_serp_features(
            meta.raw if meta else None,
            pos.raw if isinstance(pos.raw, dict) else None,
        )
        keyword_payloads.append(
            {
                "client_id": job.client_id,
                "site_engine_id": engine_id,
                "keyword_id": keyword_id,
                "keyword": keyword_text.strip(),
                "group_id": meta.group_id if meta else None,
                "group_name": meta.group_name if meta else None,
                "volume": (meta.volume if meta and meta.volume is not None else pos.volume),
                "current_position": pos.position,
                "previous_position": prev_pos,
                "ranking_change": pos.position_change,
                "visibility": pos.visibility,
                "earned_serp_features": earned_serp_features,
                "ranking_url": pos.ranking_url,
                "checked_at": pos.date,
            }
        )
        seen_keys.add(key)

    for key, meta in keyword_meta.items():
        if key in seen_keys:
            continue
        if not meta.keyword or not meta.keyword.strip():
            continue
        engine_id, keyword_id = key
        keyword_payloads.append(
            {
                "client_id": job.client_id,
                "site_engine_id": engine_id or "",
                "keyword_id": keyword_id,
                "keyword": meta.keyword.strip(),
                "group_id": meta.group_id,
                "group_name": meta.group_name,
                "volume": meta.volume,
                "current_position": None,
                "previous_position": None,
                "ranking_change": None,
                "visibility": None,
                "earned_serp_features": merge_earned_serp_features(meta.raw if meta else None),
                "ranking_url": None,
                "checked_at": None,
            }
        )

    ranking_payloads: list[dict[str, Any]] = []
    for row in positions:
        if row.date is None or not row.keyword_id or not row.site_engine_id:
            continue
        keyword_text = row.keyword
        if not keyword_text:
            meta = keyword_meta.get((row.site_engine_id, row.keyword_id))
            keyword_text = meta.keyword if meta else None
        if not keyword_text or not keyword_text.strip():
            continue
        ranking_payloads.append(
            {
                "client_id": job.client_id,
                "date": row.date,
                "site_engine_id": row.site_engine_id,
                "keyword_id": row.keyword_id,
                "keyword": keyword_text.strip(),
                "position": row.position,
                "position_change": row.position_change,
                "volume": row.volume,
                "ranking_url": row.ranking_url,
                "visibility": row.visibility,
            }
        )

    competitor_payloads: list[dict[str, Any]] = []
    for row in competitors:
        if not row.competitor_id:
            continue
        competitor_payloads.append(
            {
                "client_id": job.client_id,
                "site_engine_id": row.site_engine_id or "",
                "competitor_id": row.competitor_id,
                "name": row.name,
                "url": row.url,
                "visibility": row.visibility,
                "metric_date": row.metric_date,
            }
        )

    for batch in _chunked(keyword_payloads, UPSERT_BATCH_SIZE):
        if not batch:
            continue
        stmt = insert(FactSerKeyword).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_facts_ser_keywords_grain",
            set_={
                "keyword": stmt.excluded.keyword,
                "group_id": stmt.excluded.group_id,
                "group_name": stmt.excluded.group_name,
                "volume": stmt.excluded.volume,
                "current_position": stmt.excluded.current_position,
                "previous_position": stmt.excluded.previous_position,
                "ranking_change": stmt.excluded.ranking_change,
                "visibility": stmt.excluded.visibility,
                "earned_serp_features": stmt.excluded.earned_serp_features,
                "ranking_url": stmt.excluded.ranking_url,
                "checked_at": stmt.excluded.checked_at,
            },
        )
        db.execute(stmt)

    for batch in _chunked(ranking_payloads, UPSERT_BATCH_SIZE):
        if not batch:
            continue
        stmt = insert(FactSerRanking).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_facts_ser_rankings_grain",
            set_={
                "keyword": stmt.excluded.keyword,
                "position": stmt.excluded.position,
                "position_change": stmt.excluded.position_change,
                "volume": stmt.excluded.volume,
                "ranking_url": stmt.excluded.ranking_url,
                "visibility": stmt.excluded.visibility,
            },
        )
        db.execute(stmt)

    for batch in _chunked(competitor_payloads, UPSERT_BATCH_SIZE):
        if not batch:
            continue
        stmt = insert(FactSerCompetitor).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_facts_ser_competitors_grain",
            set_={
                "name": stmt.excluded.name,
                "url": stmt.excluded.url,
                "visibility": stmt.excluded.visibility,
                "metric_date": stmt.excluded.metric_date,
            },
        )
        db.execute(stmt)

    summary_payloads: list[dict[str, Any]] = []
    for row in summaries:
        if row.metric_date is None:
            continue
        summary_payloads.append(
            {
                "client_id": job.client_id,
                "metric_date": row.metric_date,
                "visibility": row.visibility,
                "visibility_percent": row.visibility_percent,
                "top5": row.top5,
                "top10": row.top10,
                "top30": row.top30,
            }
        )

    for batch in _chunked(summary_payloads, UPSERT_BATCH_SIZE):
        if not batch:
            continue
        stmt = insert(FactSerSiteSummary).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_facts_ser_site_summary_grain",
            set_={
                "visibility": stmt.excluded.visibility,
                "visibility_percent": stmt.excluded.visibility_percent,
                "top5": stmt.excluded.top5,
                "top10": stmt.excluded.top10,
                "top30": stmt.excluded.top30,
            },
        )
        db.execute(stmt)

    db.commit()
    return len(keyword_payloads), len(ranking_payloads), len(competitor_payloads), len(summary_payloads)
