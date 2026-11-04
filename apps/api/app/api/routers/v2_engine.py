"""The v2 Decision Engine: candidate lists for the focus a client is working on."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.decisions import leads_candidates, traffic_candidates, visibility_candidates
from app.models.client import Client
from app.services import crawl_link_facts, data_freshness, growth_action, llm_evidence, page_diagnostic
from app.services.monthly_review import last_complete_month, parse_month

router = APIRouter(prefix="/v2/engine", tags=["v2 engine"])


@router.get("/freshness")
def data_freshness_for(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    """The newest data each source holds for this client."""
    return data_freshness.build(db, client)


@router.get("/visibility")
def visibility_candidates_for(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[str | None, Query(description="The last of the three months to read, YYYY-MM")] = None,
    bucket_id: UUID | None = None,
) -> dict:
    chosen = month or last_complete_month()
    try:
        parse_month(chosen)
        return visibility_candidates.build(db, client, chosen, bucket_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _focus_list(module, client: Client, db: Session, month: str | None, bucket_id: UUID | None) -> dict:
    chosen = month or last_complete_month()
    try:
        parse_month(chosen)
        return module.build(db, client, chosen, bucket_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/traffic")
def traffic_candidates_for(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[str | None, Query(description="The complete month to judge, YYYY-MM")] = None,
    bucket_id: UUID | None = None,
) -> dict:
    """Where organic sessions fell, judged against the site's own trend."""
    return _focus_list(traffic_candidates, client, db, month, bucket_id)


@router.get("/leads")
def leads_candidates_for(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[str | None, Query(description="The last of the three months to read, YYYY-MM")] = None,
    bucket_id: UUID | None = None,
) -> dict:
    """Pages whose organic visitors convert or engage less than the site's own norm."""
    return _focus_list(leads_candidates, client, db, month, bucket_id)


@router.get("/visibility/buckets")
def visibility_bucket_overview(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[str | None, Query()] = None,
    focus_bucket_id: UUID | None = None,
) -> dict:
    """How much each watchlist bucket has to move, side by side, and advice on the focus bucket."""
    chosen = month or last_complete_month()
    try:
        parse_month(chosen)
        return visibility_candidates.bucket_overview(
            db, client, chosen, str(focus_bucket_id) if focus_bucket_id else None
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


MAX_DIAGNOSED = 5


class Selection(BaseModel):
    search: str = Field(min_length=1, max_length=400)
    page: str = Field(min_length=1, max_length=2048)


class DiagnoseRequest(BaseModel):
    month: str | None = None
    selections: list[Selection] = Field(min_length=1, max_length=MAX_DIAGNOSED)


def _evidence(db: Session, client: Client, month: str, search: str, page: str) -> dict:
    found = visibility_candidates.page_evidence(db, client, month, search, page)
    found["crawl"] = crawl_link_facts.link_facts(db, client, page, found["donors"])
    found["llm"] = llm_evidence.for_search(db, client, search)
    found["brand_keys"] = visibility_candidates.brand_keys(client)
    return found


@router.post("/diagnose")
def diagnose_selected(
    payload: DiagnoseRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Read each ticked page live and run the Visibility rules on it.

    The numbers for a pair are recomputed from Search Console here. Only pages on the client's
    own site are fetched, and the fetch goes through the crawler's public-addresses-only transport.
    """
    month = payload.month or last_complete_month()
    try:
        parse_month(month)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    results = []
    for pick in payload.selections:
        row = visibility_candidates.lookup_pair(db, client, month, pick.search, pick.page)
        if row is None:
            results.append(
                {
                    "search": pick.search,
                    "page": pick.page,
                    "read": {"ok": False, "error": "That search and page are not in this client's Search Console data."},
                    "observations": [],
                    "prescriptions": [],
                    "not_judged": [],
                    "suggestions": [],
                    "skipped_suggestions": [],
                }
            )
            continue
        results.append(
            page_diagnostic.diagnose(
                search=row["search"],
                url=pick.page,
                row=row,
                client_domain=client.domain,
                fetch=page_diagnostic._fetch,
                evidence=_evidence(db, client, month, row["search"], pick.page),
            )
        )
    return {"month": month, "results": results}


class PageDiagnoseRequest(BaseModel):
    focus: Literal["traffic", "leads"]
    month: str | None = None
    pages: list[str] = Field(min_length=1, max_length=MAX_DIAGNOSED)


def _page_evidence(db: Session, client: Client, month: str, focus: str, url: str, leads: dict | None) -> dict:
    """What a Traffic or Leads page's own suggestions are built from."""
    if focus == "traffic":
        return {"lost": traffic_candidates.queries_lost(db, client, month, url)}
    row = next((c for c in (leads or {}).get("candidates", []) if c["page"] == url), None)
    return {
        "row": row,
        "site": (leads or {}).get("site") or {},
        "noun": (leads or {}).get("noun"),
        "path": leads_candidates.conversion_path(db, client, url),
        "summary": row,
    }


@router.post("/diagnose-page")
def diagnose_selected_pages(
    payload: PageDiagnoseRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Read each ticked Traffic or Leads page live and say what is worth checking on it."""
    month = payload.month or last_complete_month()
    try:
        parse_month(month)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    leads = leads_candidates.build(db, client, month, list_size=None) if payload.focus == "leads" else None
    results = [
        page_diagnostic.diagnose_page(
            focus=payload.focus, url=url, client_domain=client.domain, fetch=page_diagnostic._fetch,
            evidence=_page_evidence(db, client, month, payload.focus, url, leads),
        )
        for url in payload.pages
    ]
    return {"month": month, "focus": payload.focus, "results": results}


class GrowthActionRequest(BaseModel):
    month: str | None = None
    keyword: str = Field(min_length=1, max_length=400)
    #: A page of the topic to use instead of the one the tool recommends.
    page: str | None = Field(default=None, max_length=2048)
    #: Which list the candidate came from, and its page. When the page worked is the candidate's own, a Traffic or
    #: Leads page's own suggestions join the action so they appear once.
    focus: Literal["visibility", "traffic", "leads"] = "visibility"
    candidate_page: str | None = Field(default=None, max_length=2048)


def _month_or_last(month: str | None) -> str:
    month = month or last_complete_month()
    try:
        parse_month(month)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return month


@router.get("/topic-for")
def topic_for(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[str, Query(min_length=1, max_length=2048)],
    search: str = "",
    month: str | None = None,
) -> dict:
    """The topic a candidate belongs to, and the pages that show for it with the one to work on first."""
    month = _month_or_last(month)
    topic = growth_action.resolve_topic(db, client, month, search, page)
    if topic["keyword"] is None:
        return {**topic, "pages": None}
    return {**topic, "pages": growth_action.topic_pages(db, client, month, topic["keyword"], include=page)}


@router.get("/topic-pages")
def topic_pages(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    keyword: Annotated[str, Query(min_length=1, max_length=400)],
    month: str | None = None,
) -> dict:
    """The pages that show for a topic and the one to work on first, with the numbers behind the choice."""
    return growth_action.topic_pages(db, client, _month_or_last(month), keyword)


@router.post("/growth-action")
def build_growth_action(
    payload: GrowthActionRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Read the page for the topic live and bundle what applies into one growth action, as a task draft."""
    month = _month_or_last(payload.month)
    extras: list[dict] = []
    if payload.focus != "visibility" and payload.candidate_page:
        topic = growth_action.topic_pages(db, client, month, payload.keyword)
        worked = payload.page or topic["recommended"]
        if worked == payload.candidate_page:
            leads = leads_candidates.build(db, client, month, list_size=None) if payload.focus == "leads" else None
            own = page_diagnostic.diagnose_page(
                focus=payload.focus, url=worked, client_domain=client.domain, fetch=page_diagnostic._fetch,
                evidence=_page_evidence(db, client, month, payload.focus, worked, leads),
            )
            extras = own.get("suggestions") or []
    bundle = growth_action.build(
        db,
        client,
        month,
        payload.keyword,
        page=payload.page,
        diagnose=lambda search, url, row, evidence: page_diagnostic.diagnose(
            search=search, url=url, row=row, client_domain=client.domain, fetch=page_diagnostic._fetch, evidence=evidence
        ),
        evidence_for=lambda search, url: _evidence(db, client, month, search, url),
        extra_suggestions=extras,
    )
    if bundle["ok"]:
        bundle["draft"] = growth_action.draft(bundle, _next_month(month))
    return bundle


def _next_month(month: str) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    return f"{year + (mon == 12):04d}-{(mon % 12) + 1:02d}"
