from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.ingestion.seranking.engines import label_engine
from app.ingestion.seranking.features import label_earned_serp_features
from app.models.client import Client
from app.models.seranking import FactSerAiPrompt, FactSerKeyword

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
