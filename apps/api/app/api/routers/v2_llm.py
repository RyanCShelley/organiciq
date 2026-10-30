"""LLM visibility for v2: runs of the watchlist's paired prompts, and the reports built from them."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.llm_visibility import platforms, report, runner
from app.models.client import Client
from app.models.llm_visibility import ClientLlmSettings, LlmRun
from app.schemas import SyncJobCreate
from app.services.competitors import bare_domain
from app.services.jobs import OverlappingJobError, enqueue_sync_job
from datetime import date

router = APIRouter(prefix="/v2/llm", tags=["v2 llm visibility"])


class CompetitorIn(BaseModel):
    domain: str
    name: str = Field(min_length=1, max_length=120)
    patterns: list[str] = Field(min_length=1, max_length=10)


class SettingsIn(BaseModel):
    brand_name: str = Field(min_length=1, max_length=255)
    brand_patterns: list[str] = Field(min_length=1, max_length=10)
    competitors: list[CompetitorIn] = Field(default_factory=list, max_length=10)


def _clean(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for v in values:
        text = " ".join(v.lower().split())
        if text:
            seen[text] = None
    return list(seen)


@router.get("/settings")
def get_llm_settings(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """What a run will use: the brand and competitor patterns, the prompts, and the platforms that have a key."""
    config = runner.brand_config(db, client)
    prompts = runner.prompts_for(db, client)
    enabled = platforms.enabled_platforms()
    return {
        "brand_name": config.brand_name,
        "brand_patterns": config.brand_patterns,
        "domain": config.domain,
        "competitors": [
            {"domain": bare_domain(d), "name": name, "patterns": patterns}
            for d, (name, patterns) in zip(client.competitor_domains or [], config.competitors)
        ],
        "prompts": len(prompts),
        "clusters": sorted({p["cluster"] for p in prompts}),
        "platforms": [{"key": p, "name": platforms.DISPLAY[p], "enabled": p in enabled} for p in platforms.PLATFORMS],
        "calls_per_run": len(prompts) * len(enabled),
    }


@router.put("/settings")
def save_llm_settings(
    payload: SettingsIn,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    own = {bare_domain(d) for d in client.competitor_domains or []}
    competitors: dict[str, dict] = {}
    for c in payload.competitors:
        domain = bare_domain(c.domain)
        if domain not in own:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{domain} is not one of this client's competitors.")
        patterns = _clean(c.patterns)
        if not patterns:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{c.name} needs at least one name to look for.")
        competitors[domain] = {"name": c.name.strip(), "patterns": patterns}
    patterns = _clean(payload.brand_patterns)
    if not patterns:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The brand needs at least one name to look for.")
    row = db.query(ClientLlmSettings).filter(ClientLlmSettings.client_id == client.id).one_or_none()
    if row is None:
        row = ClientLlmSettings(client_id=client.id)
        db.add(row)
    row.brand_name, row.brand_patterns, row.competitors = payload.brand_name.strip(), patterns, competitors
    db.commit()
    return get_llm_settings(client, _, db)


@router.get("/overview")
def llm_overview(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    run_id: UUID | None = None,
) -> dict:
    return report.overview(db, client, runner.brand_config(db, client).brand_name, run_id)


@router.get("/runs/{run_id}/responses")
def llm_run_responses(
    run_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    run = db.query(LlmRun).filter(LlmRun.id == run_id, LlmRun.client_id == client.id).one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That run is not on this client.")
    return report.run_responses(db, run)


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
def start_llm_run(
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Queue a run for the worker. It takes minutes, so the screen polls the overview."""
    if not runner.prompts_for(db, client):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This client's watchlist has no paired AI prompts to ask.")
    if not platforms.enabled_platforms():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No AI platform has an API key on this install. Add one in the API's environment.")
    try:
        job = enqueue_sync_job(
            db, client.id, SyncJobCreate(source=runner.SOURCE, start_date=date.today(), end_date=date.today(), params={"triggered_by": user.email})
        )
    except OverlappingJobError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A run is already queued or running for this client.") from exc
    return {"job_id": str(job.id), "status": "queued"}
