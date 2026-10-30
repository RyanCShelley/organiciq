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
from app.services import crawl_link_facts, page_diagnostic
from app.services.monthly_review import last_complete_month, parse_month

router = APIRouter(prefix="/v2/engine", tags=["v2 engine"])


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
    results = []
    for url in payload.pages:
        if payload.focus == "traffic":
            evidence = {"lost": traffic_candidates.queries_lost(db, client, month, url)}
        else:
            row = next((c for c in (leads or {}).get("candidates", []) if c["page"] == url), None)
            evidence = {
                "row": row,
                "site": (leads or {}).get("site") or {},
                "noun": (leads or {}).get("noun"),
                "path": leads_candidates.conversion_path(db, client, url),
                "summary": row,
            }
        results.append(
            page_diagnostic.diagnose_page(
                focus=payload.focus, url=url, client_domain=client.domain, fetch=page_diagnostic._fetch, evidence=evidence
            )
        )
    return {"month": month, "focus": payload.focus, "results": results}
