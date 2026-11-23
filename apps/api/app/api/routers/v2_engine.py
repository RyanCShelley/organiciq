"""The v2 Decision Engine: candidate lists for the focus a client is working on."""

from __future__ import annotations

from datetime import date

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.decisions import action_context as ac
from app.decisions import leads_candidates, traffic_candidates, visibility_candidates
from app.decisions.faq_links import faq_schema_urls, find_faq_page
from app.models.client import Client
from app.services import crawl_fallback, crawl_link_facts, data_freshness, growth_action, llm_evidence, page_diagnostic, page_history, search_signals, winners
from app.services.memo import Memo

#: Who is winning for a term and page, kept for an hour: reading the winners' pages and comparing them is the slow, paid part.
_WINNERS = Memo(size=64, ttl=3600.0)
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
        found = visibility_candidates.build(db, client, chosen, bucket_id)
        # When each listed page was last read by the site crawl, so a row can say its page was read long ago before anyone diagnoses it.
        from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot

        urls = {c["page"] for c in found["candidates"]}
        read_on = dict(
            db.query(FactCrawlPageSnapshot.normalized_url, FactCrawlPageSnapshot.snapshot_date).filter(
                FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot.normalized_url.in_(urls)
            )
        ) if urls else {}
        for c in found["candidates"]:
            day = read_on.get(c["page"])
            c["page_crawled_on"] = day.isoformat() if day else None
        return found
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
    focus: Literal["visibility", "traffic", "leads"] | None = None
    selections: list[Selection] = Field(min_length=1, max_length=MAX_DIAGNOSED)


def _evidence(db: Session, client: Client, month: str, search: str, page: str) -> dict:
    found = visibility_candidates.page_evidence(db, client, month, search, page)
    found["crawl"] = crawl_link_facts.link_facts(db, client, page, found["donors"])
    found["llm"] = llm_evidence.for_search(db, client, search)
    found["brand_keys"] = visibility_candidates.brand_keys(client)
    return found


def _top_nonbrand_search(db: Session, client: Client, month: str, page_url: str) -> str | None:
    from sqlalchemy import func
    from app.models.gsc import FactGscQueryPage

    year, mon = int(month[:4]), int(month[5:7])
    start, end = visibility_candidates.windows(date(year, mon, 1))["current"]
    q = func.lower(func.trim(FactGscQueryPage.query))
    rows = (
        db.query(q, func.sum(FactGscQueryPage.impressions))
        .filter(
            FactGscQueryPage.client_id == client.id,
            FactGscQueryPage.normalized_url == page_url,
            FactGscQueryPage.date >= start,
            FactGscQueryPage.date <= end,
        )
        .group_by(q)
        .order_by(func.sum(FactGscQueryPage.impressions).desc())
        .all()
    )
    brand = visibility_candidates.brand_keys(client)
    for query_text, _ in rows:
        if query_text and not visibility_candidates.is_brand(query_text, brand):
            return query_text
    return None


@router.get("/rejection-reasons")
def list_rejection_reasons(_: Annotated[AuthUser, Depends(require_sma_staff)]) -> dict:
    """Return the 8 structured reviewer rejection reasons."""
    return {"reasons": [{"key": k, "label": v} for k, v in ac.REJECTION_REASONS.items()]}


@router.get("/page-history")
def get_page_history(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[str, Query(min_length=1, max_length=2048)],
) -> dict:
    """Aggregated crawl changes, Decision Engine tasks, and annotations for a single page URL."""
    return page_history.for_page(db, client, page)


@router.get("/serp")
def get_serp_detail(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    search: Annotated[str, Query(min_length=1, max_length=400)],
    pull: bool = False,
) -> dict:
    """Inspect (and optionally pull) DataForSEO SERP results, features, PAA questions, and intent reading."""
    return search_signals.serp_detail(db, client, search, pull=pull)


class SerpPullRequest(BaseModel):
    search: str = Field(min_length=1, max_length=400)


@router.post("/serp/pull")
def pull_serp_detail(
    payload: SerpPullRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Pull wider DataForSEO SERP data on demand for any search (including untracked GSC queries)."""
    return search_signals.serp_detail(db, client, payload.search, pull=True)


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

    active_focus = payload.focus or growth_action.active_focus(db, client, _next_month(month))
    style_notes = (getattr(client, "style_notes", None) or "").strip() or None
    site_pages_map = growth_action.site_pages(db, client)
    site_urls = list(site_pages_map) if site_pages_map is not None else None
    faq_schemas = faq_schema_urls(db, client) if site_pages_map else set()

    results = []
    for pick in payload.selections:
        row = visibility_candidates.lookup_pair(db, client, month, pick.search, pick.page)
        if row is None:
            results.append(
                {
                    "search": pick.search,
                    "page": pick.page,
                    "focus": active_focus,
                    "read": {"ok": False, "error": "That search and page are not in this client's Search Console data."},
                    "observations": [],
                    "prescriptions": [],
                    "not_judged": [],
                    "suggestions": [],
                    "skipped_suggestions": [],
                }
            )
            continue
        ev = _evidence(db, client, month, row["search"], pick.page)
        signals = search_signals.for_search(db, client, row["search"], pull=False)
        faq_link = find_faq_page(db, client, site_pages_map, pick.page, schema_urls=faq_schemas)
        if faq_link:
            ev["faq_link"] = faq_link
        results.append(
            page_diagnostic.diagnose(
                search=row["search"],
                url=pick.page,
                row=row,
                client_domain=client.domain,
                fetch=crawl_fallback.with_crawl(db, client),
                evidence=ev,
                focus=active_focus,
                signals=signals,
                site_urls=site_urls,
                style_notes=style_notes,
                page_history=page_history.for_page(db, client, pick.page),
            )
        )
    return {"month": month, "focus": active_focus, "results": results}


class PageDiagnoseRequest(BaseModel):
    focus: Literal["visibility", "traffic", "leads"] | None = None
    month: str | None = None
    pages: list[str] = Field(min_length=1, max_length=MAX_DIAGNOSED)


def _page_evidence(db: Session, client: Client, month: str, focus: str, url: str, leads: dict | None) -> dict:
    """What a Traffic or Leads page's own suggestions are built from."""
    if focus == "traffic":
        return {"lost": traffic_candidates.queries_lost(db, client, month, url)}
    if focus == "visibility":
        return {}
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
    """Read each ticked page live and say what is worth checking on it."""
    month = payload.month or last_complete_month()
    try:
        parse_month(month)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    active_focus = payload.focus or growth_action.active_focus(db, client, _next_month(month))
    style_notes = (getattr(client, "style_notes", None) or "").strip() or None
    site_pages_map = growth_action.site_pages(db, client)
    site_urls = list(site_pages_map) if site_pages_map is not None else None
    faq_schemas = faq_schema_urls(db, client) if site_pages_map else set()

    leads = leads_candidates.build(db, client, month, list_size=None) if active_focus == "leads" else None
    results = []
    for url in payload.pages:
        top_search = _top_nonbrand_search(db, client, month, url)
        signals = search_signals.for_search(db, client, top_search, pull=False) if top_search else None
        faq_link = find_faq_page(db, client, site_pages_map, url, schema_urls=faq_schemas)
        history = page_history.for_page(db, client, url)

        if active_focus == "visibility" and top_search:
            row = visibility_candidates.lookup_pair(db, client, month, top_search, url)
            if row is not None:
                ev = _evidence(db, client, month, row["search"], url)
                if faq_link:
                    ev["faq_link"] = faq_link
                results.append(
                    page_diagnostic.diagnose(
                        search=row["search"],
                        url=url,
                        row=row,
                        client_domain=client.domain,
                        fetch=crawl_fallback.with_crawl(db, client),
                        evidence=ev,
                        focus=active_focus,
                        signals=signals,
                        site_urls=site_urls,
                        style_notes=style_notes,
                        page_history=history,
                    )
                )
                continue

        ev = _page_evidence(db, client, month, active_focus, url, leads)
        if top_search:
            ev["search"] = top_search
            ctr_row = visibility_candidates.lookup_pair(db, client, month, top_search, url)
            if ctr_row is not None:
                ev["ctr_row"] = ctr_row
                ev["page_queries"] = visibility_candidates.page_evidence(db, client, month, top_search, url).get("page_queries") or []
        if faq_link:
            ev["faq_link"] = faq_link
        results.append(
            page_diagnostic.diagnose_page(
                focus=active_focus,
                url=url,
                client_domain=client.domain,
                fetch=crawl_fallback.with_crawl(db, client),
                evidence=ev,
                signals=signals,
                site_urls=site_urls,
                style_notes=style_notes,
                page_history=history,
            )
        )
    return {"month": month, "focus": active_focus, "results": results}


class GrowthActionRequest(BaseModel):
    month: str | None = None
    keyword: str = Field(min_length=1, max_length=400)
    #: A page of the topic to use instead of the one the tool recommends.
    page: str | None = Field(default=None, max_length=2048)
    #: Which list the candidate came from, and its page. Defaults to active ClientFocus if omitted.
    focus: Literal["visibility", "traffic", "leads"] | None = None
    candidate_page: str | None = Field(default=None, max_length=2048)
    #: The search the person selected. The results page read, and everything built from it, is this search's and no other's.
    search: str | None = Field(default=None, max_length=400)


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
    term = " ".join(search.lower().split())
    if term and not term.startswith("("):
        # A search was selected: the pages listed are the ones that show for that search, not for the whole watchlist keyword.
        signals = search_signals.for_search(db, client, term, pull=False)
        return {**topic, "search": term, "pages": growth_action.topic_pages(db, client, month, term, include=page, signals=signals, exact=True)}
    return {**topic, "search": None, "pages": growth_action.topic_pages(db, client, month, topic["keyword"], include=page)}


@router.get("/topic-pages")
def topic_pages(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    keyword: Annotated[str, Query(min_length=1, max_length=400)],
    month: str | None = None,
) -> dict:
    """The pages that show for a topic and the one to work on first, with the numbers behind the choice."""
    return growth_action.topic_pages(db, client, _month_or_last(month), keyword, signals=search_signals.for_search(db, client, keyword, pull=False))


@router.post("/growth-action")
def build_growth_action(
    payload: GrowthActionRequest,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Read the page for the topic live and bundle what applies into one growth action, as a task draft."""
    month = _month_or_last(payload.month)
    active_focus = payload.focus or growth_action.active_focus(db, client, _next_month(month))
    extras: list[dict] = []
    if active_focus != "visibility" and payload.candidate_page:
        topic = growth_action.topic_pages(db, client, month, payload.keyword)
        worked = payload.page or topic["recommended"]
        if worked == payload.candidate_page:
            leads = leads_candidates.build(db, client, month, list_size=None) if active_focus == "leads" else None
            own = page_diagnostic.diagnose_page(
                focus=active_focus, url=worked, client_domain=client.domain, fetch=crawl_fallback.with_crawl(db, client),
                evidence=_page_evidence(db, client, month, active_focus, worked, leads),
            )
            extras = own.get("suggestions") or []
    bundle = growth_action.build(
        db,
        client,
        month,
        payload.keyword,
        page=payload.page,
        diagnose=lambda search, url, row, evidence: page_diagnostic.diagnose(
            search=search, url=url, row=row, client_domain=client.domain, fetch=crawl_fallback.with_crawl(db, client), evidence=evidence
        ),
        evidence_for=lambda search, url: _evidence(db, client, month, search, url),
        extra_suggestions=extras,
        signals_for=lambda search: search_signals.for_search(db, client, search),
        planned_month=_next_month(month),
        search=payload.search,
        winners_for=lambda search, intent, url, page_type, own, questions: _WINNERS.get(
            (str(client.id), search, url, date.today().isoformat(), intent.get("serp_date")),
            lambda: winners.gather(db, client, search=search, intent=intent, page_url=url, page_type=page_type, own=own, questions=questions),
        ),
        focus=active_focus,
    )
    if bundle.get("page"):
        bundle["page_history"] = page_history.for_page(db, client, bundle["page"])
    if bundle["ok"] and bundle["parts"]:
        bundle["draft"] = growth_action.draft(bundle, _next_month(month))
    return bundle


def _next_month(month: str) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    return f"{year + (mon == 12):04d}-{(mon % 12) + 1:02d}"
