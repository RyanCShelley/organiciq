"""Small changes to a page, written by a model from the page's own search data: the opening, the terms worked in naturally, an FAQ.

Content refreshes plans a whole page. Most of what the Decision engine asks for is smaller than that: rewrite the opening so it answers
the search, work these terms into sentences already there, add the questions people ask. Each of these is one change at one spot, so the
model is given only that spot, the searches the page already earns, and the page's own words, and returns the exact text to put in.
Nothing is sent to the site: the result is a draft to copy in.

The FAQ comes with its markup, built here from the same questions and answers (never by the model), so the visible text and the
FAQPage markup cannot disagree.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from lxml import html as lxml_html
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.client import Client
from app.models.schema_tools import ContentModelRun
from app.schema_tools import llm
from app.services import ctr_optimizer
from app.services.page_diagnostic import read_page
from app.services.schema_pages import content_text

logger = logging.getLogger("organiciq.content_optimizer")

#: What the screen offers, and what each asks the model for.
KINDS: dict[str, dict[str, str]] = {
    "opening": {"label": "Rewrite the opening", "does": "Writes a new opening that answers the search at the top of the page."},
    "terms": {"label": "Work in these terms", "does": "Finds sentences already on the page and rewords them to use the searched terms naturally."},
    "faq": {"label": "Write the FAQ", "does": "Writes the questions people ask for this page, with answers, and the FAQ markup for them."},
}
RANGE_DAYS = 90
EXCERPT_CHARS = 5000
STALE_MINUTES = 8
_FAQ_HEADING = re.compile(r"\b(faq|faqs|frequently asked|common questions|questions? (and|&) answers?)\b", re.I)


def read_spot(body: str) -> dict[str, Any]:
    """What the page says now where the model will work: its heading, its opening paragraphs, whether it already has an FAQ."""
    try:
        doc = lxml_html.fromstring(body)
    except Exception:  # noqa: BLE001 - unreadable markup is an empty page
        return {"h1": "", "opening": "", "has_faq": False, "faq_questions": []}
    for tag in ("script", "style", "nav", "footer", "header", "aside", "form", "noscript"):
        for node in doc.xpath(f"//{tag}"):
            if node.getparent() is not None:
                node.getparent().remove(node)
    h1 = " ".join(((doc.xpath("//h1") or [None])[0].text_content() if doc.xpath("//h1") else "").split())
    paragraphs = [" ".join(p.text_content().split()) for p in doc.xpath("//p")]
    opening = " ".join(p for p in paragraphs if len(p) >= 40)[:900]
    headings = [" ".join(h.text_content().split()) for h in doc.xpath("//h2|//h3")]
    faq_at = next((i for i, h in enumerate(headings) if _FAQ_HEADING.search(h)), None)
    questions = [h for h in headings if h.endswith("?")]
    has_faq = faq_at is not None or len(questions) >= 2
    return {"h1": h1, "opening": opening, "has_faq": has_faq, "faq_questions": questions[:12]}


def _rows(detail: dict[str, Any]) -> str:
    return "\n".join(
        f"- “{s['query']}”: position {s['position']}, {s['impressions']:,} impressions, {s['clicks']} clicks" for s in detail["searches"]
    ) or "(no searches with enough data)"


def _page_block(url: str, brand: str, detail: dict[str, Any], spot: dict[str, Any], text: str, start: str, end: str) -> str:
    return f"""--- PAGE ---
Address: {url}
Brand: {brand}
Title: {detail.get("title") or "(none)"}
Main heading: {spot["h1"] or "(not read)"}

--- THE SEARCHES THIS PAGE RANKS FOR ({start} to {end}, Search Console) ---
{_rows(detail)}

--- THE PAGE'S OWN WORDS (excerpt) ---
{text[:EXCERPT_CHARS] or "(the page could not be read)"}
"""


RULES = """Say only what the page's own words support. No invented prices, awards, numbers, guarantees or claims. Plain wording, no filler, no hype."""


def build_prompt(kind: str, *, url: str, brand: str, detail: dict[str, Any], spot: dict[str, Any], text: str, start: str, end: str, terms: list[str]) -> str:
    page = _page_block(url, brand, detail, spot, text, start, end)
    if kind == "opening":
        return f"""You are an editor rewriting ONLY the opening of one page, so the first lines answer what people searching for it want to know. The rest of the page stays as it is.

{page}
--- THE OPENING NOW ---
{spot["opening"] or "(no opening paragraph found)"}

--- RULES ---
1. Answer the main search in the first sentence, in the searcher's own words. Then say what the page offers and for whom.
2. Keep it to 2 to 4 sentences, about the length of the opening now. Keep the page's voice.
3. {RULES}
4. Write two options that take different approaches. For each, name the searches it serves and say in one sentence why it answers them better.

Respond with ONE JSON object, no prose and no markdown fences:
{{"diagnosis": "one or two sentences on why the opening now does not answer the searches", "options": [{{"text": "...", "serves": ["search"], "why": "..."}}]}}
"""
    if kind == "terms":
        wanted = "\n".join(f"- {t}" for t in terms) or "(none missing: use the searches above)"
        return f"""You are an editor working searched terms into ONE page without rewriting it. Find sentences already on the page and change only the words needed so a term reads naturally in them.

{page}
--- TERMS TO WORK IN (searches the page ranks for whose words are thin or missing in its text) ---
{wanted}

--- RULES ---
1. Give 3 to 6 edits. Each edit quotes ONE sentence copied exactly from the page's words above (so it can be found), and gives that sentence rewritten.
2. A term must read as a person would write it. Never stuff, never repeat a term in the same sentence, never change what the sentence means.
3. Change as little as possible. If a term has no natural place, leave it out and say so in "left_out".
4. {RULES}

Respond with ONE JSON object, no prose and no markdown fences:
{{"edits": [{{"before": "exact sentence from the page", "after": "the sentence reworded", "terms": ["term used"], "why": "..."}}], "left_out": ["term and why"]}}
"""
    known = "\n".join(f"- {q}" for q in spot["faq_questions"]) or "(none)"
    note = "The page already has an FAQ. Write only questions it does NOT already answer." if spot["has_faq"] else "The page has no FAQ yet."
    return f"""You are writing the FAQ for ONE page from the searches it already ranks for, so the questions are the ones people actually ask.

{page}
--- QUESTIONS THE PAGE ALREADY ANSWERS ---
{note}
{known}

--- RULES ---
1. Write 4 to 6 questions. Each comes from a search above (name which one) or from what that search is really asking.
2. Each answer is 1 to 3 sentences, answers the question directly in the first sentence, and uses only what the page's own words support. If the page does not say, do not write that question.
3. Plain text answers, no links, no markup.
4. {RULES}

Respond with ONE JSON object, no prose and no markdown fences:
{{"items": [{{"question": "...", "answer": "...", "from_search": "..."}}]}}
"""


def faq_markup(items: list[dict[str, str]]) -> str:
    """FAQPage markup for exactly these questions and answers."""
    return json.dumps(
        {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": i["question"], "acceptedAnswer": {"@type": "Answer", "text": i["answer"]}} for i in items]},
        indent=2, ensure_ascii=False,
    )


def missing_terms(detail: dict[str, Any], text: str) -> list[str]:
    """Searches the page earns that its own words do not contain as a phrase."""
    low = " ".join(text.lower().split())
    out = []
    for s in detail["searches"]:
        q = " ".join(s["query"].lower().split())
        if q and q not in low:
            out.append(s["query"])
    return out[:8]


def clean(kind: str, parsed: dict[str, Any], *, spot: dict[str, Any], text: str) -> dict[str, Any]:
    """Keep only what can be used: options with text, edits whose quoted sentence really is on the page, questions with answers."""
    if kind == "opening":
        options = []
        for o in parsed.get("options") or []:
            t = " ".join(str(o.get("text") or "").split()) if isinstance(o, dict) else ""
            if t and t != spot["opening"]:
                options.append({"text": t, "serves": [str(x)[:200] for x in (o.get("serves") or []) if x][:5], "why": str(o.get("why") or "")[:400]})
        return {"before": spot["opening"], "diagnosis": str(parsed.get("diagnosis") or "")[:600], "options": options[:3]}
    if kind == "terms":
        flat = " ".join(text.split())
        edits = []
        for e in parsed.get("edits") or []:
            if not isinstance(e, dict):
                continue
            before, after = " ".join(str(e.get("before") or "").split()), " ".join(str(e.get("after") or "").split())
            if before and after and before != after and before in flat:
                edits.append({"before": before, "after": after, "terms": [str(x)[:120] for x in (e.get("terms") or []) if x][:4], "why": str(e.get("why") or "")[:300]})
        return {"edits": edits[:6], "left_out": [str(x)[:300] for x in (parsed.get("left_out") or []) if x][:6]}
    items = []
    for i in parsed.get("items") or []:
        if isinstance(i, dict):
            q, a = " ".join(str(i.get("question") or "").split()), " ".join(str(i.get("answer") or "").split())
            if q and a:
                items.append({"question": q if q.endswith("?") else q + "?", "answer": a, "from_search": str(i.get("from_search") or "")[:200]})
    items = items[:6]
    return {"items": items, "markup": faq_markup(items) if items else "", "already_has_faq": spot["has_faq"]}


def start(db: Session, client: Client, kind: str, url: str, depth: str, who: str) -> ContentModelRun:
    row = ContentModelRun(client_id=client.id, kind=kind, key=url, depth=depth, status="running", created_by=who, payload={})
    db.add(row)
    db.commit()
    return row


def latest(db: Session, client: Client, kind: str, url: str) -> dict[str, Any] | None:
    from datetime import datetime, timezone

    row = db.query(ContentModelRun).filter(ContentModelRun.client_id == client.id, ContentModelRun.kind == kind, ContentModelRun.key == url).order_by(ContentModelRun.created_at.desc()).first()
    if row is None:
        return None
    if row.status == "running" and row.created_at < datetime.now(timezone.utc) - timedelta(minutes=STALE_MINUTES):
        row.status, row.error = "failed", "This was interrupted (the API restarted). Run it again."
        db.commit()
    return {"id": str(row.id), "kind": kind, "status": row.status, "error": row.error, "depth": row.depth, "cost_usd": float(row.cost_usd or 0), "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None, **(row.payload or {})}


def run(run_id: UUID) -> None:
    """Write the change for a started run, in the background; the screen polls the row."""
    db = SessionLocal()
    try:
        row = db.get(ContentModelRun, run_id)
        if row is None:
            return
        client = db.get(Client, row.client_id)
        end = date.today()
        start_d = end - timedelta(days=RANGE_DAYS)
        detail = ctr_optimizer.page_detail(db, client, row.key, start_d, end)
        if not detail["searches"]:
            raise RuntimeError("This page has no searches with enough data in the last 90 days, so there is nothing to write from.")
        try:
            found = read_page(row.key, client.domain)
            body = found.body if 200 <= found.status < 300 else ""
        except Exception:  # noqa: BLE001 - the screen says the page could not be read
            body = ""
        if not body:
            raise RuntimeError("The page could not be read, so there is no text to work on. Check that the address loads, then run it again.")
        from app.models.llm_visibility import ClientLlmSettings

        brand = (db.query(ClientLlmSettings.brand_name).filter(ClientLlmSettings.client_id == client.id).scalar() or client.client_name or "").strip()
        spot, text = read_spot(body), content_text(body)
        prompt = build_prompt(row.kind, url=row.key, brand=brand, detail=detail, spot=spot, text=text, start=start_d.isoformat(), end=end.isoformat(), terms=missing_terms(detail, text))
        reply, t_in, t_out = llm.call(row.depth, prompt, max_tokens=6000)
        parsed = llm.extract_json(reply)
        if not isinstance(parsed, dict):
            raise llm.ModelError("The answer was not in the expected form. Run it again.")
        result = clean(row.kind, parsed, spot=spot, text=text)
        if not any(result.get(k) for k in ("options", "edits", "items")):
            raise llm.ModelError("The model gave nothing that can be used as written. Run it again, or try a deeper setting.")
        row.payload = {**result, "url": row.key, "searches_used": len(detail["searches"]), "from": start_d.isoformat(), "to": end.isoformat()}
        row.cost_usd, row.status = Decimal(str(llm.cost(row.depth, t_in, t_out))), "done"
        db.commit()
    except Exception as exc:  # noqa: BLE001 - the failure is the result; the screen shows it
        db.rollback()
        row = db.get(ContentModelRun, run_id)
        if row is not None:
            logger.exception("Content optimizer run failed")
            row.status, row.error = "failed", str(exc)[:500]
            db.commit()
    finally:
        db.close()
