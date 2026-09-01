from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.ingestion.seranking import client as ser_client
from app.ingestion.seranking.tracker_stats import presence_from_statistics, weighted_presence
from app.models.integration import Integration, IntegrationProvider
from app.models.job import SyncJob
from app.models.seranking import StagingSerAiCheck, StagingSerAiPrompt, StagingSerAiTrackerStats


def _api_key() -> str:
    key = get_settings().se_ranking_api_key.strip()
    if not key:
        raise RuntimeError("SE_RANKING_API_KEY not configured")
    return key


def _load_integration(db: Session, client_id: UUID) -> Integration:
    integration = (
        db.query(Integration)
        .filter(
            Integration.client_id == client_id,
            Integration.provider == IntegrationProvider.SE_RANKING,
        )
        .one_or_none()
    )
    if integration is None:
        raise RuntimeError("SE Ranking integration row missing")
    if not integration.external_property_id:
        raise RuntimeError("SE Ranking project is not selected")
    return integration


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_intent(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        codes = [str(item).strip() for item in value if str(item).strip()]
        return codes or None
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return None


def fetch_seranking_ai(db: Session, job: SyncJob) -> tuple[int, int]:
    integration = _load_integration(db, job.client_id)
    api_key = _api_key()
    site_id = integration.external_property_id or ""

    llm_engines = ser_client.list_airt_llm_engines(api_key, site_id)
    if not llm_engines:
        raise RuntimeError("No SE Ranking AI engines configured for this project")

    groups = ser_client.list_airt_prompt_groups(api_key, site_id)
    group_names = {
        _as_str(group.get("id")): _as_str(group.get("name"))
        for group in groups
        if _as_str(group.get("id"))
    }

    db.query(StagingSerAiPrompt).filter(StagingSerAiPrompt.job_id == job.id).delete()
    db.query(StagingSerAiCheck).filter(StagingSerAiCheck.job_id == job.id).delete()

    prompt_rows = 0
    check_rows = 0

    for engine in llm_engines:
        llm_id = _as_str(engine.get("id"))
        base_name = _as_str(engine.get("base_name")) or "unknown"
        if not llm_id:
            continue

        prompts = ser_client.list_airt_prompts_paginated(
            api_key=api_key,
            site_id=site_id,
            llm_id=llm_id,
        )
        rankings = ser_client.list_airt_prompt_rankings_paginated(
            api_key=api_key,
            site_id=site_id,
            llm_id=llm_id,
            date_from=job.start_date,
            date_to=job.end_date,
        )
        rankings_by_prompt_id = {
            _as_str(item.get("prompt_id")): item for item in rankings if _as_str(item.get("prompt_id"))
        }

        seen_prompt_ids: set[str] = set()
        for item in prompts:
            prompt_id = _as_str(item.get("prompt_id"))
            prompt_text = _as_str(item.get("prompt"))
            if not prompt_id or not prompt_text:
                continue
            group_id = _as_str(item.get("group_id"))
            ranking = rankings_by_prompt_id.get(prompt_id, {})
            search_intent = _as_intent(ranking.get("search_intent")) or _as_intent(item.get("intent_meaning"))
            db.add(
                StagingSerAiPrompt(
                    job_id=job.id,
                    client_id=job.client_id,
                    raw={"prompt": item, "ranking": ranking},
                    llm_id=llm_id,
                    prompt_id=prompt_id,
                    prompt_llm_id=_as_str(item.get("prompt_llm_id")),
                    engine=base_name,
                    prompt=prompt_text,
                    group_id=group_id,
                    group_name=group_names.get(group_id) if group_id else None,
                    search_volume=_as_decimal(ranking.get("search_volume") or item.get("search_volume")),
                    search_intent=search_intent,
                )
            )
            prompt_rows += 1
            seen_prompt_ids.add(prompt_id)

        for ranking in rankings:
            prompt_id = _as_str(ranking.get("prompt_id"))
            prompt_text = _as_str(ranking.get("prompt"))
            if not prompt_id or not prompt_text:
                continue
            if prompt_id not in seen_prompt_ids:
                group_id = None
                db.add(
                    StagingSerAiPrompt(
                        job_id=job.id,
                        client_id=job.client_id,
                        raw={"ranking": ranking},
                        llm_id=llm_id,
                        prompt_id=prompt_id,
                        prompt_llm_id=None,
                        engine=base_name,
                        prompt=prompt_text,
                        group_id=group_id,
                        group_name=None,
                        search_volume=_as_decimal(ranking.get("search_volume")),
                        search_intent=_as_intent(ranking.get("search_intent")),
                    )
                )
                prompt_rows += 1
                seen_prompt_ids.add(prompt_id)

            positions = ranking.get("positions")
            if not isinstance(positions, list):
                continue
            for pos in positions:
                if not isinstance(pos, dict):
                    continue
                pos_date = _as_date(pos.get("date"))
                if pos_date is None:
                    continue
                db.add(
                    StagingSerAiCheck(
                        job_id=job.id,
                        client_id=job.client_id,
                        raw=pos,
                        date=pos_date,
                        llm_id=llm_id,
                        prompt_id=prompt_id,
                        prompt=prompt_text,
                        url_position=_as_decimal(pos.get("url_position")),
                        mention_position=_as_decimal(pos.get("mention_position")),
                        urls_count=_as_decimal(pos.get("urls_count")),
                        mentions_count=_as_decimal(pos.get("mentions_count")),
                        organic_overlap_percent=_as_decimal(pos.get("organic_overlap_percent")),
                    )
                )
                check_rows += 1

    db.commit()
    return prompt_rows, check_rows


def fetch_seranking_ai_tracker_stats(db: Session, job: SyncJob) -> int:
    """Fetch AIRT mention/link presence stats for tracked prompts from SE Ranking."""
    integration = _load_integration(db, job.client_id)
    api_key = _api_key()
    site_id = integration.external_property_id or ""

    llm_engines = ser_client.list_airt_llm_engines(api_key, site_id)
    if not llm_engines:
        return 0

    db.query(StagingSerAiTrackerStats).filter(StagingSerAiTrackerStats.job_id == job.id).delete()

    all_rows: list[tuple[int, float | None, float | None]] = []
    top3_rows: list[tuple[int, float | None, float | None]] = []
    raw_payload: dict[str, object] = {"engines": []}

    for engine in llm_engines:
        llm_id = _as_str(engine.get("id"))
        if not llm_id:
            continue

        all_stats = ser_client.get_airt_llm_statistics(
            api_key=api_key,
            site_id=site_id,
            llm_id=llm_id,
            date_from=job.start_date,
            date_to=job.end_date,
            top=0,
        )
        top3_stats = ser_client.get_airt_llm_statistics(
            api_key=api_key,
            site_id=site_id,
            llm_id=llm_id,
            date_from=job.start_date,
            date_to=job.end_date,
            top=3,
        )
        mention_all, link_all, prompts = presence_from_statistics(all_stats)
        mention_top3, link_top3, _ = presence_from_statistics(top3_stats)
        if prompts:
            all_rows.append((prompts, mention_all, link_all))
            top3_rows.append((prompts, mention_top3, link_top3))
        raw_payload["engines"].append(
            {
                "llm_id": llm_id,
                "engine": _as_str(engine.get("base_name")),
                "all_positions": all_stats,
                "top_3": top3_stats,
            }
        )

    mention_presence, link_presence = weighted_presence(all_rows)
    mention_top3, link_top3 = weighted_presence(top3_rows)
    total_prompts = sum(prompts for prompts, _, _ in all_rows)

    db.add(
        StagingSerAiTrackerStats(
            job_id=job.id,
            client_id=job.client_id,
            raw=raw_payload,
            metric_date=job.end_date,
            prompts_count=total_prompts or None,
            mention_presence_pct=_as_decimal(mention_presence),
            link_presence_pct=_as_decimal(link_presence),
            mention_top3_pct=_as_decimal(mention_top3),
            link_top3_pct=_as_decimal(link_top3),
        )
    )
    db.commit()
    return 1
