"""Schema and knowledge graph for v2."""

from __future__ import annotations

import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ask import engine
from app.core.client_scope import require_client
from app.core.db import get_db
from app.core.security import AuthUser, require_sma_staff
from app.core.settings import get_settings
from app.models.client import Client
from app.models.schema_tools import ClientSchemaConcept, ClientSchemaIgnore
from app.services import schema_audit, schema_pages

router = APIRouter(prefix="/v2/schema", tags=["v2 schema"])


@router.get("")
def schema_and_knowledge_graph(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """What the crawl found, by kind of page, and whether the brand reads as one entity. `data` is null when the site was not crawled."""
    return {"data": schema_audit.audit(db, client), "ready": bool(get_settings().anthropic_api_key.strip()), "depths": {k: v[0] for k, v in engine.DEPTHS.items()}}


class SearchIn(BaseModel):
    names: list[str] = Field(min_length=1, max_length=10)


@router.post("/concepts/search")
def search_concepts(payload: SearchIn, _: Annotated[AuthUser, Depends(require_sma_staff)], client: Annotated[Client, Depends(require_client)]) -> dict:
    """Wikidata items for each name, so the right one can be approved."""
    names = [n.strip() for n in payload.names if n.strip()]
    return {"candidates": schema_pages.search_concepts(names)}


class ConceptIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    qid: str = Field(pattern=r"^Q\d+$")
    label: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=1000)


@router.post("/concepts")
def approve_concept(
    payload: ConceptIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    row = schema_pages.approve_concept(db, client, payload.name, payload.qid, payload.label, payload.description, user.email)
    return schema_audit._concept_out(row)


@router.delete("/concepts/{concept_id}")
def remove_concept(
    concept_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    row = db.query(ClientSchemaConcept).filter(ClientSchemaConcept.id == concept_id, ClientSchemaConcept.client_id == client.id).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That concept is not on this client.")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/page")
def page(
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
    url: Annotated[str, Query(min_length=8, max_length=2048)],
) -> dict:
    """What the crawl holds for a page and the latest audit and markup written for it."""
    stored = schema_pages.stored_page(db, client, url)
    audit = stored["audit"]
    return {
        "url": url, "page_type": audit["page_type"], "present": audit["present"], "missing_required": audit["missing_required"],
        "missing_recommended": audit["missing_recommended"], "corrections": audit["corrections"], "score": audit["score"],
        "existing": [json.dumps(b, indent=2, ensure_ascii=False)[:6000] for b in stored["blocks"][:3]],
        "reports": schema_pages.latest_reports(db, client, url),
    }


class PageIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    depth: Literal["quick", "deep", "deepest"] = "quick"


def _start(kind: str, payload: PageIn, background: BackgroundTasks, client: Client, user: AuthUser, db: Session) -> dict:
    if not get_settings().anthropic_api_key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The Anthropic key is not set on this install, so the model cannot be asked.")
    cap = get_settings().ask_monthly_cap_usd
    if float(schema_pages.month_spend(db, client)) >= cap:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"This client has used its ${cap:.0f} for model questions this month. The limit resets on the 1st.")
    row = schema_pages.start_report(db, client, payload.url, kind, payload.depth, user.email)
    background.add_task(schema_pages.run_report, row.id)
    return {"id": str(row.id)}


@router.post("/page/audit", status_code=status.HTTP_202_ACCEPTED)
def audit_page(payload: PageIn, background: BackgroundTasks, client: Annotated[Client, Depends(require_client)], user: Annotated[AuthUser, Depends(require_sma_staff)], db: Annotated[Session, Depends(get_db)]) -> dict:
    """Have the model audit one page: its intent, what is wrong, a fix plan, and concepts to link to Wikidata."""
    return _start("audit", payload, background, client, user, db)


@router.post("/page/markup", status_code=status.HTTP_202_ACCEPTED)
def generate_markup(payload: PageIn, background: BackgroundTasks, client: Annotated[Client, Depends(require_client)], user: Annotated[AuthUser, Depends(require_sma_staff)], db: Annotated[Session, Depends(get_db)]) -> dict:
    """Have the model write corrected JSON-LD for one page, linking only to the Wikidata items approved for this client."""
    return _start("markup", payload, background, client, user, db)


class IgnoreIn(BaseModel):
    scope: Literal["check", "expect", "page_type", "page", "cleanup"]
    key: str = Field(min_length=1, max_length=2048)
    label: str = Field(default="", max_length=500)


@router.post("/ignores")
def add_ignore(
    payload: IgnoreIn,
    client: Annotated[Client, Depends(require_client)],
    user: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Say that something does not apply to this client, so the Schema screen stops counting it. It can be restored."""
    row = db.query(ClientSchemaIgnore).filter(ClientSchemaIgnore.client_id == client.id, ClientSchemaIgnore.scope == payload.scope, ClientSchemaIgnore.key == payload.key).one_or_none()
    if row is None:
        row = ClientSchemaIgnore(client_id=client.id, scope=payload.scope, key=payload.key, label=payload.label, created_by=user.email)
        db.add(row)
        db.commit()
    return {"id": str(row.id)}


@router.delete("/ignores/{ignore_id}")
def remove_ignore(
    ignore_id: UUID,
    client: Annotated[Client, Depends(require_client)],
    _: Annotated[AuthUser, Depends(require_sma_staff)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    row = db.query(ClientSchemaIgnore).filter(ClientSchemaIgnore.id == ignore_id, ClientSchemaIgnore.client_id == client.id).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That is not ignored for this client.")
    db.delete(row)
    db.commit()
    return {"ok": True}
