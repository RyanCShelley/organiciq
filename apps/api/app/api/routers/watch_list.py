from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.ingestion.seranking.engines import label_engine
from app.ingestion.seranking.features import label_earned_serp_features
from app.ingestion.seranking.client import (
    AI_SEARCH_CREDITS_PER_PROMPT,
    ai_search_limit_for,
)
from app.models.client import Client
from app.models.seranking import (
    FactSerAiPrompt,
    FactSerAiSearchPrompt,
    FactSerDomainKeyword,
    FactSerKeyword,
)

router = APIRouter(prefix="/watch-list", tags=["watch-list"])


@router.get("/search")
def search_watch_list(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    rows = (
        db.query(FactSerKeyword)
        .filter(FactSerKeyword.client_id == client.id)
        .order_by(FactSerKeyword.keyword.asc())
        .limit(5000)
        .all()
    )
    return [
        {
            "keyword_id": r.keyword_id,
            "keyword": r.keyword,
            "group_name": r.group_name,
            "site_engine_id": r.site_engine_id,
            "volume": float(r.volume) if r.volume is not None else None,
            "current_position": float(r.current_position) if r.current_position is not None else None,
            "previous_position": float(r.previous_position) if r.previous_position is not None else None,
            "ranking_change": float(r.ranking_change) if r.ranking_change is not None else None,
            "earned_serp_features": label_earned_serp_features(r.earned_serp_features),
            "ranking_url": r.ranking_url,
            "checked_at": r.checked_at.isoformat() if r.checked_at else None,
        }
        for r in rows
    ]


def _ai_answer_site_id(db: Session, client: Client) -> str | None:
    from app.models.integration import Integration, IntegrationProvider

    row = (
        db.query(Integration)
        .filter(
            Integration.client_id == client.id,
            Integration.provider == IntegrationProvider.SE_RANKING,
        )
        .one_or_none()
    )
    return row.external_property_id if row else None


@router.get("/ai/answer")
def ai_prompt_answer(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    prompt_id: str,
    on: str | None = None,
) -> dict:
    """What the model actually said, and which URLs it cited.

    Fetched when somebody opens a row rather than synced. The answer is one
    API call per prompt per day, and 24 clients at 40 prompts is a thousand
    calls a day for something almost nobody opens — so the cost is paid by
    the person asking.

    The rankings we do sync carry a position and a count and no URL: "cited
    at 2 of 9" with nothing to open.
    """
    from datetime import date as _date

    from app.core.settings import get_settings
    from app.ingestion.seranking.client import get_airt_prompt_answer

    row = (
        db.query(FactSerAiPrompt)
        .filter(
            FactSerAiPrompt.client_id == client.id,
            FactSerAiPrompt.prompt_id == prompt_id,
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="No such prompt for this client.")
    if not row.prompt_llm_id or not row.llm_id:
        return {
            "available": False,
            "reason": "This prompt predates the ids the answer lookup needs.",
        }

    site_id = _ai_answer_site_id(db, client)
    api_key = (get_settings().se_ranking_api_key or "").strip()
    if not site_id or not api_key:
        return {"available": False, "reason": "SE Ranking is not connected for this client."}

    when = _date.today()
    if on:
        try:
            when = _date.fromisoformat(on)
        except ValueError:
            raise HTTPException(status_code=422, detail="`on` must be YYYY-MM-DD.")
    elif row.checked_at:
        when = row.checked_at.date() if hasattr(row.checked_at, "date") else row.checked_at

    try:
        answer = get_airt_prompt_answer(
            api_key=api_key,
            site_id=site_id,
            llm_id=row.llm_id,
            prompt_llm_id=row.prompt_llm_id,
            on=when,
        )
    except Exception as exc:  # noqa: BLE001 — a missing answer is not an error
        # SE Ranking keeps a year of answers and 400s past that, and a day
        # with no check has none. Neither is worth a 500 on a panel somebody
        # opened out of curiosity.
        return {
            "available": False,
            "reason": f"No cached answer for {when.isoformat()}.",
            "detail": str(exc)[:200],
        }

    return {
        "available": True,
        "date": answer.get("date") or when.isoformat(),
        "prompt": answer.get("prompt") or row.prompt,
        "text": answer.get("text"),
        # The whole point: which URLs the model cited, in the order it cited
        # them, and who it named alongside.
        "sources": [
            {"url": item.get("url"), "position": item.get("position")}
            for item in (answer.get("sources") or [])
            if isinstance(item, dict) and item.get("url")
        ],
        "brands": [
            {"name": item.get("name"), "position": item.get("position")}
            for item in (answer.get("brands") or [])
            if isinstance(item, dict) and item.get("name")
        ],
    }


@router.get("/ai")
def ai_watch_list(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    rows = (
        db.query(FactSerAiPrompt)
        .filter(FactSerAiPrompt.client_id == client.id)
        .order_by(FactSerAiPrompt.prompt.asc())
        .limit(5000)
        .all()
    )
    return [
        {
            "prompt_id": r.prompt_id,
            "prompt": r.prompt,
            "engine": label_engine(r.engine),
            "group_name": r.group_name,
            "search_volume": float(r.search_volume) if r.search_volume is not None else None,
            "search_intent": r.search_intent or [],
            "url_position": float(r.url_position) if r.url_position is not None else None,
            "mention_position": float(r.mention_position) if r.mention_position is not None else None,
            "url_position_change": float(r.url_position_change) if r.url_position_change is not None else None,
            "mention_position_change": (
                float(r.mention_position_change) if r.mention_position_change is not None else None
            ),
            "brand_mentioned": r.brand_mentioned,
            "brand_cited": r.brand_cited,
            "citation_url": r.citation_url,
            "ai_visibility": float(r.ai_visibility) if r.ai_visibility is not None else None,
            "ai_sov": float(r.ai_sov) if r.ai_sov is not None else None,
            "checked_at": r.checked_at.isoformat() if r.checked_at else None,
        }
        for r in rows
    ]


@router.get("/untracked")
def untracked_keywords(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 200,
) -> dict:
    """
    Keywords the domain ranks for that the watch list does not track.

    The difference is computed here rather than stored, so adding a keyword to
    tracking removes it from this list without re-running the fetch — which
    costs 100 SE Ranking credits.
    """
    tracked = {
        (row[0] or "").strip().lower()
        for row in db.query(FactSerKeyword.keyword).filter(
            FactSerKeyword.client_id == client.id
        )
    }

    rows = (
        db.query(FactSerDomainKeyword)
        .filter(FactSerDomainKeyword.client_id == client.id)
        .order_by(FactSerDomainKeyword.volume.desc().nullslast())
        .all()
    )

    untracked = [row for row in rows if (row.keyword or "").strip().lower() not in tracked]
    fetched_at = rows[0].fetched_at.isoformat() if rows and rows[0].fetched_at else None

    return {
        "fetched_at": fetched_at,
        "domain_keywords": len(rows),
        "tracked_keywords": len(tracked),
        "untracked_total": len(untracked),
        "items": [
            {
                "keyword": row.keyword,
                "position": float(row.position) if row.position is not None else None,
                "volume": float(row.volume) if row.volume is not None else None,
                "difficulty": float(row.difficulty) if row.difficulty is not None else None,
                "traffic": float(row.traffic) if row.traffic is not None else None,
                "ranking_url": row.ranking_url,
                "serp_features": row.serp_features or [],
            }
            for row in untracked[:limit]
        ],
    }


@router.get("/untracked-prompts")
def untracked_prompts(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 200,
) -> dict:
    """
    Prompts the brand appears in that the watch list does not track.

    Mirrors /untracked for keywords: the difference is computed here, so adding
    a prompt to tracking drops it from this list without re-running a lookup
    that costs 200 credits per prompt.
    """
    tracked = {
        (row[0] or "").strip().lower()
        for row in db.query(FactSerAiPrompt.prompt).filter(
            FactSerAiPrompt.client_id == client.id
        )
    }

    rows = (
        db.query(FactSerAiSearchPrompt)
        .filter(FactSerAiSearchPrompt.client_id == client.id)
        .order_by(FactSerAiSearchPrompt.volume.desc().nullslast())
        .all()
    )

    untracked = [row for row in rows if (row.prompt or "").strip().lower() not in tracked]
    by_engine: dict[str, str | None] = {}
    for row in rows:
        if row.engine not in by_engine:
            by_engine[row.engine] = row.fetched_at.isoformat() if row.fetched_at else None

    return {
        # The UI bounds its prompt-count options to this rather than guessing.
        "max_prompts": ai_search_limit_for(client.ai_search_prompt_limit),
        "credits_per_prompt": AI_SEARCH_CREDITS_PER_PROMPT,
        "engines_fetched": by_engine,
        "discovered_prompts": len(rows),
        "tracked_prompts": len(tracked),
        "untracked_total": len(untracked),
        "items": [
            {
                "prompt": row.prompt,
                "engine": row.engine,
                "volume": float(row.volume) if row.volume is not None else None,
                "appearance_type": row.appearance_type,
                "answer_links": row.answer_links or [],
            }
            for row in untracked[:limit]
        ],
    }
