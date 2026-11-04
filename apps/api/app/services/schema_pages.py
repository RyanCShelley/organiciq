"""On-demand work on one page: a model-written audit with Wikidata candidates, and corrected markup built from approved concepts.

Both are the Topic Hub tool's two calls (`app.schema_tools.prompts`). The model suggests concept *names*; the Wikidata lookup, not the
model, supplies the item numbers; and generated markup may link only to the items a person has approved for the client.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from lxml import html as lxml_html
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ask import engine
from app.core.db import SessionLocal
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSchema, FactCrawlPageSnapshot
from app.models.schema_tools import ClientSchemaConcept, SchemaPageReport
from app.schema_tools import llm, wikidata
from app.schema_tools.prompts import build_audit_prompt, build_generate_prompt
from app.schema_tools.transforms import run_pipeline
from app.services import schema_audit
from app.services.page_diagnostic import PageUnreadable, read_page

logger = logging.getLogger("organiciq.schema_pages")

#: Elements that are chrome, not content (the same set the crawler leaves out of a word count).
_CHROME = ("script", "style", "noscript", "template", "svg", "nav", "header", "footer", "menu")
STALE_MINUTES = 8


def content_text(body: str) -> str:
    """The page's own words, without scripts, navigation and footers."""
    try:
        doc = lxml_html.fromstring(body)
    except Exception:  # noqa: BLE001 - unreadable markup is an empty page, not a failure
        return ""
    for tag in _CHROME:
        for node in doc.xpath(f"//{tag}"):
            node.getparent().remove(node) if node.getparent() is not None else None
    return " ".join((doc.text_content() or "").split())


def key_of(name: str) -> str:
    return " ".join((name or "").lower().split())


def drop_placeholder_profiles(parsed: Any) -> list[str]:
    """Remove sameAs links that are only a site's front page (https://www.instagram.com/): the model fills these in when it does not
    know the brand's real profile, and a link to nobody's profile is worse than none."""
    notes: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for i in node:
                walk(i)
        elif isinstance(node, dict):
            same = node.get("sameAs")
            if same is not None:
                items = same if isinstance(same, list) else [same]
                keep = [u for u in items if not (isinstance(u, str) and urlsplit(u).path in ("", "/") and "wikidata" not in u)]
                for u in items:
                    if u not in keep:
                        notes.append(f"Removed sameAs link {u}: it points to a site's front page, not to this brand's profile. Add the real profile address.")
                if keep:
                    node["sameAs"] = keep if isinstance(same, list) else keep[0]
                else:
                    node.pop("sameAs", None)
            for v in node.values():
                walk(v)

    walk(parsed)
    return notes


# ── concepts ──────────────────────────────────────────────────────────────────


def search_concepts(names: list[str]) -> dict[str, list[dict[str, str]]]:
    found = asyncio.run(wikidata.search_many(names))
    return {name: [c.to_dict() for c in cands] for name, cands in found.items()}


def approve_concept(db: Session, client: Client, name: str, qid: str, label: str, description: str, who: str) -> ClientSchemaConcept:
    row = db.query(ClientSchemaConcept).filter(ClientSchemaConcept.client_id == client.id, ClientSchemaConcept.name_key == key_of(name)).one_or_none()
    if row is None:
        row = ClientSchemaConcept(client_id=client.id, name=name.strip(), name_key=key_of(name), approved_by=who)
        db.add(row)
    row.qid, row.label, row.description, row.approved_by = qid, label, description, who
    db.commit()
    return row


# ── spend ─────────────────────────────────────────────────────────────────────


from app.services.model_spend import month_spend  # noqa: E402,F401  (the same total for every feature that asks the model)


# ── one page ──────────────────────────────────────────────────────────────────


def stored_page(db: Session, client: Client, url: str) -> dict[str, Any]:
    """What the crawl holds for a page: its markup, its type, and what the deterministic audit finds."""
    snap = db.query(FactCrawlPageSnapshot).filter(FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot.normalized_url == url).first()
    rows = db.query(FactCrawlPageSchema).filter(FactCrawlPageSchema.client_id == client.id, FactCrawlPageSchema.normalized_url == url).all()
    blocks = [r.raw for r in rows if r.syntax == "json_ld" and not r.parse_error and r.raw]
    micro = {r.schema_type for r in rows if r.syntax != "json_ld" and r.schema_type}
    # The site's other pages decide whether a reference to an entity this page does not define is dangling or defined elsewhere.
    everywhere: dict[str, list[Any]] = {}
    for r in db.query(FactCrawlPageSchema).filter(FactCrawlPageSchema.client_id == client.id, FactCrawlPageSchema.syntax == "json_ld").all():
        if not r.parse_error and r.raw:
            everywhere.setdefault(r.normalized_url, []).append(r.raw)
    audit = schema_audit.audit_page(url, snap.title if snap else None, blocks, micro, schema_audit.site_registry(everywhere))
    audit = schema_audit.apply_ignores(audit, schema_audit.load_ignores(db, client)) or {**audit, "ignored_page": True}
    audit["findings"] = [f.as_dict() for f in audit.get("findings", [])]
    return {"snapshot_title": snap.title if snap else None, "blocks": blocks, "audit": audit}


def latest_reports(db: Session, client: Client, url: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kind in ("audit", "markup"):
        row = db.query(SchemaPageReport).filter(SchemaPageReport.client_id == client.id, SchemaPageReport.url == url, SchemaPageReport.kind == kind).order_by(SchemaPageReport.created_at.desc()).first()
        if row is not None:
            if row.status == "running" and row.created_at < datetime.now(timezone.utc) - timedelta(minutes=STALE_MINUTES):
                row.status, row.error = "failed", "This was interrupted (the API restarted). Run it again."
                db.commit()
            out[kind] = report_out(row)
    return out


def report_out(row: SchemaPageReport) -> dict[str, Any]:
    return {"id": str(row.id), "kind": row.kind, "status": row.status, "error": row.error, "depth": row.depth, "cost_usd": float(row.cost_usd or 0), "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None, **(row.payload or {})}


def start_report(db: Session, client: Client, url: str, kind: str, depth: str, who: str) -> SchemaPageReport:
    row = SchemaPageReport(client_id=client.id, url=url, kind=kind, depth=depth, status="running", created_by=who, payload={})
    db.add(row)
    db.commit()
    return row


def run_report(report_id: UUID) -> None:
    """Do the work for a started report, in the background; the screen polls the row."""
    db = SessionLocal()
    try:
        row = db.get(SchemaPageReport, report_id)
        if row is None:
            return
        client = db.get(Client, row.client_id)
        found = read_page(row.url, client.domain)
        if not 200 <= found.status < 300:
            raise PageUnreadable(f"The page answered with status {found.status}, so it was not read.")
        text = content_text(found.body)
        stored = stored_page(db, client, row.url)
        page_type, present = stored["audit"]["page_type"], stored["audit"]["present"]
        title = stored["snapshot_title"] or ""
        approved = {c.name: c.qid for c in db.query(ClientSchemaConcept).filter(ClientSchemaConcept.client_id == client.id)}
        if row.kind == "audit":
            prompt = build_audit_prompt(
                page_url=row.url, page_type=page_type, title=title, cleaned_content=text, present_schema_types=stored["audit"]["present_jsonld"],
                parse_error_count=0, has_jsonld=bool(stored["blocks"]), existing_jsonld=stored["blocks"] or None,
            )
            reply, t_in, t_out = llm.call(row.depth, prompt, max_tokens=3000)
            parsed = llm.extract_json(reply)
            if not isinstance(parsed, dict):
                raise llm.ModelError("The audit was not written in the expected form. Run it again.")
            names = [str(c).strip() for c in parsed.get("suggested_concepts") or [] if isinstance(c, str) and c.strip()]
            candidates = asyncio.run(wikidata.search_many(names)) if names else {}
            approved_lower = {k.lower(): v for k, v in approved.items()}
            row.payload = {
                "page_type": page_type, "present_before": present, "intent": str(parsed.get("intent") or ""), "intent_explanation": str(parsed.get("intent_explanation") or ""),
                "diagnosis": [str(d) for d in parsed.get("diagnosis") or [] if d], "fix_plan": [str(s) for s in parsed.get("fix_plan") or [] if s],
                "concepts": [{"name": n, "approved_qid": approved_lower.get(n.lower(), ""), "candidates": [c.to_dict() for c in candidates.get(n, [])]} for n in names],
            }
        else:
            origin = f"https://{schema_audit.bare_domain(client.domain)}"
            prompt = build_generate_prompt(
                page_url=row.url, page_type=page_type, title=title, cleaned_content=text, site_origin=origin,
                organization_name=client.client_name, approved_qids=[{"name": n, "qid": q} for n, q in approved.items()], existing_jsonld=stored["blocks"] or None,
            )
            reply, t_in, t_out = llm.call(row.depth, prompt, max_tokens=3500)
            parsed, notes = llm.strip_breadcrumbs(llm.extract_json(reply))
            notes = notes + drop_placeholder_profiles(parsed)
            cleaned, corrections = run_pipeline(parsed)
            row.payload = {
                "json_ld": json.dumps(cleaned, indent=2, ensure_ascii=False), "approved": [{"name": n, "qid": q} for n, q in approved.items()],
                "post_corrections": notes + [f"{c['transform']}: {c['detail']}" for c in corrections], "page_type": page_type,
            }
        row.cost_usd, row.status = Decimal(str(llm.cost(row.depth, t_in, t_out))), "done"
        db.commit()
    except Exception as exc:  # noqa: BLE001 - the failure is the result; the screen shows it
        db.rollback()
        row = db.get(SchemaPageReport, report_id)
        if row is not None:
            logger.exception("Schema page report failed")
            row.status, row.error = "failed", str(exc)[:500]
            db.commit()
    finally:
        db.close()
