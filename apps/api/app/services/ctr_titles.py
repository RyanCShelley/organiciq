"""Title tags written by a model from a page's own search data.

The model is given what a person writing the title would want: the searches the page already ranks for, with their position,
impressions and click-through against what the benchmark expects, the title and description now, the page's own words, and the
pattern the site's other titles follow. It writes three options that differ in approach, each saying which searches it serves.
Titles are checked here (length, repeats, the current title) so nothing comes back that cannot be used. The result is a draft for a
person: it is not sent anywhere and does not use the month's page allowance.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from lxml import html as lxml_html
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.client import Client
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.schema_tools import CtrTitleDraft
from app.schema_tools import llm
from app.services import ctr_optimizer
from app.services.page_diagnostic import read_page
from app.services.schema_pages import content_text

logger = logging.getLogger("organiciq.ctr_titles")

TITLE_LIMIT = 60
OPTIONS = 3
STALE_MINUTES = 8
EXCERPT_CHARS = 3500
_SEPARATORS = re.compile(r"\s+[|–—-]\s+|:\s+")


def title_pattern(db: Session, client: Client) -> dict[str, Any]:
    """How the site's titles usually end (a brand after a separator), and how long they usually are."""
    titles = [t.strip() for (t,) in db.query(FactCrawlPageSnapshot.title).filter(FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.source == CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot.status_code == 200) if t and t.strip()]
    if not titles:
        return {"suffix": None, "typical_length": None, "titles": 0}
    ends: Counter[str] = Counter()
    for t in titles:
        parts = _SEPARATORS.split(t)
        if len(parts) > 1:
            ends[parts[-1].strip()] += 1
    suffix = None
    if ends:
        common, n = ends.most_common(1)[0]
        suffix = common if n >= 5 and n / len(titles) >= 0.3 else None
    lengths = sorted(len(t) for t in titles)
    return {"suffix": suffix, "typical_length": lengths[len(lengths) // 2], "titles": len(titles)}


def _h1(body: str) -> str:
    try:
        node = lxml_html.fromstring(body).xpath("//h1")
        return " ".join((node[0].text_content() if node else "").split())
    except Exception:  # noqa: BLE001
        return ""


def build_prompt(*, url: str, brand: str, detail: dict[str, Any], h1: str, content: str, pattern: dict[str, Any], start: str, end: str) -> str:
    rows = "\n".join(
        f"- “{s['query']}”: position {s['position']}, {s['impressions']:,} impressions, {s['ctr']}% click-through"
        f" against {s['expected_ctr']}% expected" + (f", about {s['extra_clicks']} clicks to gain" if s["below"] else "")
        + (f". Bing: {s['bing']['clicks']} clicks of {s['bing']['impressions']:,} impressions" if s.get("bing") else "")
        for s in detail["searches"]
    ) or "(no searches with enough data)"
    suffix = f"Most of this site's titles end with “{pattern['suffix']}” after a separator." if pattern.get("suffix") else "The site's titles do not follow one clear ending."
    current = detail.get("title") or ""
    return f"""You are an SEO copywriter improving the title tag of ONE page so it earns more clicks from the searches it already ranks for. The page's rankings stay as they are: you are improving how well the title matches and sells to the people searching.

--- PAGE ---
Address: {url}
Brand: {brand}
Title now ({len(current)} characters): {current or "(none)"}
Meta description now: {detail.get("description") or "(none)"}
Main heading: {h1 or "(not read)"}

--- THE SEARCHES THIS PAGE RANKS FOR ({start} to {end}, Search Console) ---
Brand searches are left out on purpose. The benchmark is what a page at that position usually earns.
{rows}

--- WHAT THE SITE'S TITLES LOOK LIKE ---
{suffix} A typical title here is about {pattern.get("typical_length") or "?"} characters.

--- THE PAGE'S OWN WORDS (excerpt) ---
{content[:EXCERPT_CHARS] or "(the page could not be read, so rely on the title, description and searches above)"}

--- RULES ---
1. Each title is {TITLE_LIMIT} characters or fewer, counting the brand ending if you keep one. Shorter is fine.
2. Keep the main terms the page already ranks for, near the front. Do not drop a term that earns impressions.
3. Make the searches that earn less than expected look answered: say what the page is (a product, a collection, a guide) in the searcher's own words, and give a reason to choose it.
4. Say only what the page's content supports. No invented prices, discounts, awards, numbers or claims. No clickbait, no ALL CAPS, no repeated words.
5. Keep the site's title pattern (the ending) where it fits within the limit; drop it only when that is the only way to fit the limit.
6. Write three options that take different approaches (for example: lead with the exact searched term; lead with the benefit; lead with what the page is). Each must be a title someone could use as written.
7. For each option, name the searches it serves (from the list above) and say in one sentence why it should earn more clicks.
8. Start with a one or two sentence diagnosis of why the title now earns fewer clicks than its position should.

Respond with ONE JSON object, no prose before or after and no markdown fences, exactly this shape:
{{"diagnosis": "...", "options": [{{"title": "...", "serves": ["search one", "search two"], "why": "..."}}], "recommended": 0}}
"recommended" is the index (0 to 2) of the option you would use first.
"""


def clean_options(parsed: dict[str, Any], current: str | None) -> tuple[list[dict[str, Any]], int]:
    """The options a person can use: whitespace tidied, no repeats, not the title now, with the length of each worked out here."""
    seen = {" ".join((current or "").lower().split())}
    options: list[dict[str, Any]] = []
    recommended_title = None
    raw = parsed.get("options") if isinstance(parsed.get("options"), list) else []
    rec = parsed.get("recommended")
    for i, o in enumerate(raw):
        if not isinstance(o, dict):
            continue
        title = " ".join(str(o.get("title") or "").replace("“", '"').replace("”", '"').strip().strip('"').split())
        key = title.lower()
        if not title or key in seen:
            continue
        seen.add(key)
        if rec == i:
            recommended_title = title
        options.append({"title": title, "length": len(title), "too_long": len(title) > TITLE_LIMIT, "why": str(o.get("why") or "")[:400], "serves": [str(x)[:200] for x in (o.get("serves") or []) if x][:6]})
    options = options[:OPTIONS]
    index = next((i for i, o in enumerate(options) if o["title"] == recommended_title), 0)
    return options, index


def start(db: Session, client: Client, url: str, depth: str, start_date: date, end_date: date, who: str) -> CtrTitleDraft:
    row = CtrTitleDraft(client_id=client.id, url=url, depth=depth, status="running", range_from=start_date.isoformat(), range_to=end_date.isoformat(), created_by=who, payload={})
    db.add(row)
    db.commit()
    return row


def latest(db: Session, client: Client, url: str) -> dict[str, Any] | None:
    row = db.query(CtrTitleDraft).filter(CtrTitleDraft.client_id == client.id, CtrTitleDraft.url == url).order_by(CtrTitleDraft.created_at.desc()).first()
    if row is None:
        return None
    if row.status == "running" and row.created_at < datetime.now(timezone.utc) - timedelta(minutes=STALE_MINUTES):
        row.status, row.error = "failed", "This was interrupted (the API restarted). Run it again."
        db.commit()
    return {"id": str(row.id), "status": row.status, "error": row.error, "depth": row.depth, "cost_usd": float(row.cost_usd or 0), "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None, "from": row.range_from, "to": row.range_to, **(row.payload or {})}


def run(draft_id: UUID) -> None:
    """Write the options for a started draft, in the background; the screen polls the row."""
    db = SessionLocal()
    try:
        row = db.get(CtrTitleDraft, draft_id)
        if row is None:
            return
        client = db.get(Client, row.client_id)
        detail = ctr_optimizer.page_detail(db, client, row.url, date.fromisoformat(row.range_from), date.fromisoformat(row.range_to))
        if not detail["searches"]:
            raise RuntimeError("This page has no searches with enough data in this range, so there is nothing to write the title from. Try a longer range.")
        page_read = True
        try:
            found = read_page(row.url, client.domain)
            body = found.body if 200 <= found.status < 300 else ""
            page_read = bool(body)
        except Exception:  # noqa: BLE001 - the title can still be written from the data; the note says so
            body, page_read = "", False
        from app.models.llm_visibility import ClientLlmSettings

        brand = (db.query(ClientLlmSettings.brand_name).filter(ClientLlmSettings.client_id == client.id).scalar() or client.client_name or "").strip()
        pattern = title_pattern(db, client)
        prompt = build_prompt(url=row.url, brand=brand, detail=detail, h1=_h1(body), content=content_text(body), pattern=pattern, start=row.range_from, end=row.range_to)
        reply, t_in, t_out = llm.call(row.depth, prompt, max_tokens=6000)
        parsed = llm.extract_json(reply)
        if not isinstance(parsed, dict):
            raise llm.ModelError("The title options were not written in the expected form. Run it again.")
        options, recommended = clean_options(parsed, detail.get("title"))
        if not options:
            raise llm.ModelError("The model gave no usable title that differs from the one now. Run it again, or try a deeper setting.")
        row.payload = {
            "title_now": detail.get("title"), "title_now_length": detail.get("title_length"), "diagnosis": str(parsed.get("diagnosis") or "")[:600],
            "options": options, "recommended": recommended, "searches_used": len(detail["searches"]), "page_read": page_read, "pattern": pattern.get("suffix"),
        }
        row.cost_usd, row.status = Decimal(str(llm.cost(row.depth, t_in, t_out))), "done"
        db.commit()
    except Exception as exc:  # noqa: BLE001 - the failure is the result; the screen shows it
        db.rollback()
        row = db.get(CtrTitleDraft, draft_id)
        if row is not None:
            logger.exception("CTR title draft failed")
            row.status, row.error = "failed", str(exc)[:500]
            db.commit()
    finally:
        db.close()
