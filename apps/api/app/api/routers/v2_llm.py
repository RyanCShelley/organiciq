"""LLM visibility for v2: runs of the watchlist's paired prompts, and the reports built from them."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.llm_visibility import platforms, report, runner, suggest
from app.models.client import Client
from app.models.job import SyncJob, SyncJobStatus
from app.models.llm_visibility import ClientLlmPrompt, ClientLlmSettings, LlmResponse, LlmRun
from app.schemas import SyncJobCreate
from app.services import llm_competitors
from app.services.competitors import MAX_COMPETITORS, bare_domain, clean_competitor_domains
from app.services.jobs import OverlappingJobError, enqueue_sync_job
from datetime import date

ACTIVE_JOB = (SyncJobStatus.QUEUED, SyncJobStatus.FETCHING, SyncJobStatus.STAGING, SyncJobStatus.NORMALIZING, SyncJobStatus.VALIDATING)
router = APIRouter(prefix="/v2/llm", tags=["v2 llm visibility"])


class CompetitorIn(BaseModel):
    domain: str
    name: str = Field(min_length=1, max_length=120)
    patterns: list[str] = Field(min_length=1, max_length=10)


class PromptIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=600)
    topic_cluster: str = Field(min_length=1, max_length=160)


class PromptsIn(BaseModel):
    prompts: list[PromptIn] = Field(min_length=1, max_length=50)


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
        "extra_prompts": [
            {"id": str(r.id), "prompt": r.prompt, "topic_cluster": r.topic_cluster}
            for r in db.query(ClientLlmPrompt)
            .filter(ClientLlmPrompt.client_id == client.id)
            .order_by(ClientLlmPrompt.topic_cluster, ClientLlmPrompt.created_at)
        ],
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


@router.post("/prompts")
def add_llm_prompts(
    payload: PromptsIn,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Add prompts to every run, beyond the watchlist's. One already asked (here or on the watchlist) is skipped."""
    asked = {p["prompt"].lower() for p in runner.prompts_for(db, client)}
    added = skipped = 0
    for item in payload.prompts:
        text = runner.clean_prompt(item.prompt)
        if len(text) < 3 or text.lower() in asked:
            skipped += 1
            continue
        asked.add(text.lower())
        db.add(ClientLlmPrompt(client_id=client.id, prompt=text, prompt_key=text.lower(), topic_cluster=item.topic_cluster.strip()))
        added += 1
    db.commit()
    return {"added": added, "skipped": skipped, "settings": get_llm_settings(client, _, db)}


@router.post("/prompts/suggest")
def suggest_llm_prompts(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Propose brand-check and niche questions from the client's brand, competitors, watchlist and pages. Saves nothing."""
    settings = db.query(ClientLlmSettings).filter(ClientLlmSettings.client_id == client.id).one_or_none()
    if settings is None or not settings.brand_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save the brand name and its spellings in the brand section of this Setup tab first; the questions are written around them.")
    try:
        return suggest.suggest(db, client, settings)
    except suggest.SuggestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/competitors-seen")
def competitors_seen(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Brands the AI answers named in the latest run that are not the client or a listed competitor."""
    config = runner.brand_config(db, client)
    listed = {config.brand_name, *(name for name, _ in config.competitors), *config.brand_patterns}
    return llm_competitors.seen_in_answers(db, client, listed)


class AddCompetitorIn(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    name: str = Field(min_length=1, max_length=120)


@router.post("/competitors")
def add_competitor(
    payload: AddCompetitorIn,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """List a brand seen in the AI answers as a competitor: its website joins the client's competitors (so its rankings are
    read) and its name is what later runs look for."""
    domain = bare_domain(payload.domain)
    try:
        cleaned = clean_competitor_domains([*(client.competitor_domains or []), domain], own_domain=client.domain)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This client already has {MAX_COMPETITORS} competitors, the most that are read each month. Remove one in the client's settings first.",
        ) from None
    if domain not in cleaned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{payload.domain} is not a website address.")
    client.competitor_domains = cleaned
    row = db.query(ClientLlmSettings).filter(ClientLlmSettings.client_id == client.id).one_or_none()
    if row is not None:
        row.competitors = {**(row.competitors or {}), domain: {"name": payload.name.strip(), "patterns": _clean([payload.name])}}
    db.commit()
    return get_llm_settings(client, _, db)


@router.delete("/prompts/{prompt_id}")
def remove_llm_prompt(
    prompt_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    row = db.query(ClientLlmPrompt).filter(ClientLlmPrompt.id == prompt_id, ClientLlmPrompt.client_id == client.id).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That prompt is not on this client.")
    db.delete(row)
    db.commit()
    return get_llm_settings(client, _, db)


@router.get("/overview")
def llm_overview(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    run_id: UUID | None = None,
) -> dict:
    out = report.overview(db, client, runner.brand_config(db, client).brand_name, run_id)
    # What the screen needs to show something is happening: a job queued or under way, and how far a running run has got.
    out["queued"] = db.query(SyncJob.id).filter(SyncJob.client_id == client.id, SyncJob.source == "llm_visibility", SyncJob.status.in_(ACTIVE_JOB)).first() is not None
    if out.get("running"):
        out["running"]["answered"] = db.query(func.count()).select_from(LlmResponse).filter(LlmResponse.run_id == UUID(out["running"]["id"])).scalar() or 0
    return out


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
