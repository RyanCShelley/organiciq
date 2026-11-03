"""Model drafts for the content screens: a brief for a page to write, a plan for a page to refresh, and the topics a site is missing.

The briefs and the topic finder follow Topic Hub (`v2/brief_generator.py`, `topic_gaps.py`): the model is given the evidence and asked for
a structured answer, and never for facts it cannot have (no entity ids, no figures). What it is given here is this tool's own data: the
searches, volumes and rival pages behind a gap; the lost searches, depth score and competing pages behind a refresh; the watchlist's
topics, the site's page titles and the searches it is shown for behind the topic finder.

Each is a draft for a person. Nothing is sent anywhere and no page allowance is used. Cost counts against the client's monthly model limit.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.decisions import visibility_candidates as vc
from app.models.client import Client
from app.models.gsc import FactGscQueryPage
from app.models.schema_tools import ContentModelRun, ContentState
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.schema_tools import llm
from app.services import content_gaps_view, content_refresh
from app.services.page_diagnostic import read_page
from app.services.schema_pages import content_text

logger = logging.getLogger("organiciq.content_briefs")

STALE_MINUTES = 8
EXCERPT_CHARS = 5000
TOPIC_PAGES = 80
TOPIC_SEARCHES = 80
LOOKBACK_DAYS = 90
KINDS = ("brief", "refresh", "topics")


def last_complete_month(today: date | None = None) -> str:
    today = today or date.today()
    first = today.replace(day=1) - timedelta(days=1)
    return f"{first.year:04d}-{first.month:02d}"


def start(db: Session, client: Client, kind: str, key: str, depth: str, who: str) -> ContentModelRun:
    row = ContentModelRun(client_id=client.id, kind=kind, key=key, depth=depth, status="running", created_by=who, payload={})
    db.add(row)
    db.commit()
    return row


def latest(db: Session, client: Client, kind: str, key: str) -> dict[str, Any] | None:
    row = db.query(ContentModelRun).filter(ContentModelRun.client_id == client.id, ContentModelRun.kind == kind, ContentModelRun.key == key).order_by(ContentModelRun.created_at.desc()).first()
    if row is None:
        return None
    if row.status == "running" and row.created_at < datetime.now(timezone.utc) - timedelta(minutes=STALE_MINUTES):
        row.status, row.error = "failed", "This was interrupted (the API restarted). Run it again."
        db.commit()
    return {"id": str(row.id), "status": row.status, "error": row.error, "depth": row.depth, "cost_usd": float(row.cost_usd or 0), "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None, **(row.payload or {})}


def _brand(db: Session, client: Client) -> str:
    from app.models.llm_visibility import ClientLlmSettings

    return (db.query(ClientLlmSettings.brand_name).filter(ClientLlmSettings.client_id == client.id).scalar() or client.client_name or "").strip()


def _strings(value: Any, limit: int, size: int = 300) -> list[str]:
    return [str(x).strip()[:size] for x in (value or []) if str(x).strip()][:limit] if isinstance(value, list) else []


def _dollars(row: dict[str, Any]) -> str:
    return ", ".join(f"{k} {row[k]}" for k in ("volume", "difficulty") if row.get(k) is not None)


# ---- a brief for a page to write -------------------------------------------------------------------------------------------------

def brief_prompt(*, brand: str, domain: str, gap: dict[str, Any], page_text: str) -> str:
    rivals = "\n".join(f"- {c['domain']} ranks at position {c['position']}" for c in gap["competitors"]) or "(no competitor named in settings ranks for it)"
    near = "\n".join(f"- {n['url']} — {n['title'] or 'no title'} (shares: {', '.join(n['shared']) or 'nothing'})" for n in gap["nearest"]) or "(no page shares its words)"
    shown = f"The site was shown for it {gap['impressions']:,} times in 90 days at position {gap['position']}." if gap["impressions"] else "The site has not been shown for it."
    existing = f"\nThe page that comes closest to answering it today (excerpt):\n{page_text[:2000]}\n" if page_text else ""
    return f"""You are producing a content brief for a writer at a digital marketing agency. The brief is for ONE new page (or one addition to an existing page) that targets a search the site has no page for.

Brand: {brand}
Site: {domain}
Search: “{gap['term']}”
Search data: {_dollars(gap) or 'no volume data yet'}. {shown}
Why it is a gap: {gap['why']}
Pages that rank in the top ten for it among the competitors named in settings:
{rivals}
Pages on the site closest to it:
{near}
{existing}
Respond with ONE JSON object, no prose and no markdown fences, exactly this shape:
{{"working_title": "a title tag of 55 to 62 characters that includes the search naturally",
 "page_type": "guide, comparison, service page, collection, FAQ, or another plain type",
 "angle": "two or three sentences: the specific point of view that makes this page worth ranking, concrete not generic",
 "sections": ["H2 heading", "..."],
 "questions": ["a question the page must answer", "..."],
 "entities": ["a named thing, concept or standard the page should cover, by name only", "..."],
 "target_words": 1200,
 "link_from": [{{"url": "an address from the closest pages above", "anchor_idea": "words to link with"}}],
 "avoid": ["a mistake to avoid", "..."]}}
Rules: 5 to 9 sections; 4 to 8 questions; name only things you are certain exist; use no statistics or prices you cannot see above; link_from uses only addresses listed above and may be empty; do not target the brand name."""


# ---- a plan for a page to refresh ------------------------------------------------------------------------------------------------

def refresh_prompt(*, brand: str, detail: dict[str, Any], page_text: str) -> str:
    lost = "\n".join(
        f"- “{x['query']}”: clicks {x['clicks']['previous']} → {x['clicks']['current']}, position {x['position']['previous']} → {x['position']['current']}" for x in detail["lost"]
    ) or "(no search lost enough clicks to list)"
    rivals = "\n".join(f"- “{c['query']}”: also shown: " + ", ".join(p["url"] for p in c["pages"] if p["url"] != detail["url"]) for c in detail["competing"]) or "(none)"
    depth = detail.get("depth")
    signals = ""
    if depth:
        s = depth["signals"]
        signals = f"Depth score {depth['score']} of 100. Figures, percentages or years: {s.get('stats_hits', 0)}; full dates: {s.get('dates_present', 0)}; list items: {s.get('list_items', 0)}; table: {'yes' if s.get('table_present') else 'no'}; quoted or sourced claims: {s.get('quotes', 0)}; words: {s.get('word_count')}."
    sessions = ", ".join(f"{m['month']}: {m['sessions']}" for m in detail["sessions"][-8:])
    return f"""You are an SEO editor planning the refresh of ONE existing page that has been losing organic traffic. Say what to change in the page itself so it answers the searches again. Title tags and meta descriptions are handled elsewhere: do not rewrite them.

Brand: {brand}
Page: {detail['url']}
Title: {detail.get('title') or '(none)'}
Last updated: {detail.get('last_updated') or 'unknown'}. Words: {detail.get('words') or 'unknown'}.
Organic sessions by month: {sessions}
{signals}

Searches this page lost clicks on (last three months against the three before):
{lost}

Other pages on the site shown for the same searches:
{rivals}

The page's own words (excerpt):
{page_text[:EXCERPT_CHARS] or '(the page could not be read, so plan from the data above only)'}

Respond with ONE JSON object, no prose and no markdown fences, exactly this shape:
{{"diagnosis": "two or three sentences on the most likely reasons the page lost ground, from the data above",
 "keep": ["what already works and should stay", "..."],
 "add": [{{"section": "a section or answer to add", "why": "which lost searches it wins back"}}],
 "change": [{{"what": "a specific passage or fact to update", "why": "..."}}],
 "remove": ["something to cut or move out", "..."],
 "merge_with": "the address of a page to merge into, or an empty string if the page should stay on its own",
 "target_words": 1500}}
Rules: say only what the page's words and the data support; do not invent figures, dates, quotes or sources; every item in "add" names the searches it serves; at most 6 items in each list, each item no more than 40 words."""


# ---- the topics a site is missing ------------------------------------------------------------------------------------------------

def topics_prompt(*, brand: str, domain: str, buckets: list[tuple[str, list[str]]], titles: list[str], searches: list[str], dismissed: list[str]) -> str:
    topics = "\n".join(f"- {name}: {', '.join(words[:8])}" for name, words in buckets) or "(no topics set up on the watchlist)"
    skip = "\n".join(f"- {d}" for d in dismissed) or "(none)"
    return f"""You are an SEO strategist finding the subjects a website should cover and does not. A subject is a whole topic a page, or a small group of pages, would own, not a single keyword.

Brand: {brand}
Site: {domain}

The topics the team already tracks:
{topics}

Titles of the pages that earn the most search impressions:
{chr(10).join('- ' + t for t in titles) or '(none)'}

Searches the site is shown for (brand searches removed):
{chr(10).join('- ' + s for s in searches) or '(none)'}

Subjects the team has said are NOT in scope (never suggest these or anything close):
{skip}

Find the subjects that sit next to what this site is already known for, that its audience clearly cares about, and that no page here covers. Respond with ONE JSON object, no prose and no markdown fences, exactly this shape:
{{"topics": [{{"label": "the subject in 2 to 5 words", "why": "one or two sentences: what in the data shows the audience cares and the site has no page", "content_type": "guide, comparison, service page, collection, FAQ or another plain type", "priority": "high, medium or low", "example_searches": ["a search someone would make", "..."], "next_to": "a tracked topic or page it sits beside"}}]}}
Rules: 5 to 10 subjects, most valuable first; each must be new to the site (not a rewording of a topic above); example_searches has 3 to 5 entries; make no claims about volume or difficulty."""


def topic_inputs(db: Session, client: Client) -> tuple[list[tuple[str, list[str]]], list[str], list[str]]:
    buckets = []
    for b in db.query(WatchlistBucket).filter(WatchlistBucket.client_id == client.id).order_by(WatchlistBucket.sort_order, WatchlistBucket.name):
        words = [k for (k,) in db.query(WatchlistKeyword.keyword).filter(WatchlistKeyword.bucket_id == b.id).limit(8)]
        buckets.append((b.name, words))
    start = date.today() - timedelta(days=LOOKBACK_DAYS)
    brand = vc.brand_keys(client)
    base = [FactGscQueryPage.client_id == client.id, FactGscQueryPage.date >= start]
    snaps = content_refresh._snapshots(db, client)
    pages = db.query(FactGscQueryPage.normalized_url, func.sum(FactGscQueryPage.impressions)).filter(*base).group_by(FactGscQueryPage.normalized_url).order_by(func.sum(FactGscQueryPage.impressions).desc()).limit(TOPIC_PAGES).all()
    titles = [((snaps[u].title if u in snaps else None) or u) for u, _ in pages]
    q = func.lower(func.trim(FactGscQueryPage.query))
    rows = db.query(q, func.sum(FactGscQueryPage.impressions)).filter(*base).group_by(q).order_by(func.sum(FactGscQueryPage.impressions).desc()).limit(TOPIC_SEARCHES * 3).all()
    searches = [s for s, _ in rows if s and not vc.is_brand(s, brand)][:TOPIC_SEARCHES]
    return buckets, titles, searches


def clean_topics(parsed: dict[str, Any], dismissed: set[str]) -> list[dict[str, Any]]:
    out, seen = [], {d.lower() for d in dismissed}
    for t in parsed.get("topics") if isinstance(parsed.get("topics"), list) else []:
        if not isinstance(t, dict):
            continue
        label = " ".join(str(t.get("label") or "").split())[:80]
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        priority = str(t.get("priority") or "").lower()
        out.append({"label": label, "why": str(t.get("why") or "")[:500], "content_type": str(t.get("content_type") or "")[:60], "priority": priority if priority in ("high", "medium", "low") else "medium",
                    "example_searches": _strings(t.get("example_searches"), 5, 120), "next_to": str(t.get("next_to") or "")[:120]})
    return out[:10]


# ---- running ---------------------------------------------------------------------------------------------------------------------

def _read_text(url: str, domain: str | None) -> tuple[str, str, bool]:
    try:
        found = read_page(url, domain or "")
        body = found.body if 200 <= found.status < 300 else ""
        return content_text(body), body, bool(body)
    except Exception:  # noqa: BLE001 - the draft can still be written from the data; the note says so
        return "", "", False


def run(run_id: UUID) -> None:
    """Write the draft for a started run, in the background; the screen polls the row."""
    db = SessionLocal()
    try:
        row = db.get(ContentModelRun, run_id)
        if row is None:
            return
        client = db.get(Client, row.client_id)
        brand = _brand(db, client)
        read_ok = True
        if row.kind == "brief":
            view = content_gaps_view.build(db, client)
            gap = next((g for g in view["gaps"] if g["term"] == row.key), None) or next((g for g in content_gaps_view.build(db, client, show_ignored=True)["gaps"] if g["term"] == row.key), None)
            if gap is None:
                raise RuntimeError("That search is no longer a gap, so there is nothing to brief. Reload the list.")
            text, _, read_ok = ("", "", True)
            if gap["nearest"]:
                text, _, read_ok = _read_text(gap["nearest"][0]["url"], client.domain)
            prompt = brief_prompt(brand=brand, domain=client.domain or "", gap=gap, page_text=text)
            shape = "brief"
        elif row.kind == "refresh":
            month = (row.payload or {}).get("month") or last_complete_month()
            detail = content_refresh.page_detail(db, client, month, row.key)
            text, _, read_ok = _read_text(row.key, client.domain)
            prompt = refresh_prompt(brand=brand, detail=detail, page_text=text)
            shape = "refresh"
        else:
            buckets, titles, searches = topic_inputs(db, client)
            if not titles and not searches:
                raise RuntimeError("There is no Search Console data yet, so there is nothing to find topics from. Pull the data first.")
            dismissed = sorted(content_gaps_view.ignored(db, client, "topic"))
            prompt = topics_prompt(brand=brand, domain=client.domain or "", buckets=buckets, titles=titles, searches=searches, dismissed=dismissed)
            shape = "topics"
        reply, t_in, t_out = llm.call(row.depth, prompt, max_tokens=7000)
        parsed = llm.extract_json(reply)
        if not isinstance(parsed, dict):
            raise llm.ModelError("The answer was not written in the expected form. Run it again.")
        if shape == "brief":
            payload = {
                "working_title": str(parsed.get("working_title") or "")[:120], "page_type": str(parsed.get("page_type") or "")[:60], "angle": str(parsed.get("angle") or "")[:800],
                "sections": _strings(parsed.get("sections"), 10, 160), "questions": _strings(parsed.get("questions"), 10, 200), "entities": _strings(parsed.get("entities"), 12, 100),
                "target_words": parsed.get("target_words") if isinstance(parsed.get("target_words"), int) else None, "avoid": _strings(parsed.get("avoid"), 8, 200),
                "link_from": [{"url": str(x.get("url") or ""), "anchor_idea": str(x.get("anchor_idea") or "")[:120]} for x in (parsed.get("link_from") or []) if isinstance(x, dict) and x.get("url")][:6],
            }
            if not payload["sections"]:
                raise llm.ModelError("The model gave no sections for the brief. Run it again, or try a deeper setting.")
        elif shape == "refresh":
            def pairs(items: Any, a: str, b: str) -> list[dict[str, str]]:
                return [{a: str(x.get(a) or "")[:600], b: str(x.get(b) or "")[:600]} for x in (items or []) if isinstance(x, dict) and x.get(a)][:6]

            payload = {
                "month": month, "diagnosis": str(parsed.get("diagnosis") or "")[:800], "keep": _strings(parsed.get("keep"), 6, 600), "add": pairs(parsed.get("add"), "section", "why"),
                "change": pairs(parsed.get("change"), "what", "why"), "remove": _strings(parsed.get("remove"), 6, 600), "merge_with": str(parsed.get("merge_with") or "")[:2000],
                "target_words": parsed.get("target_words") if isinstance(parsed.get("target_words"), int) else None,
            }
            if not (payload["add"] or payload["change"]):
                raise llm.ModelError("The model gave no changes for the page. Run it again, or try a deeper setting.")
        else:
            topics = clean_topics(parsed, set(dismissed))
            if not topics:
                raise llm.ModelError("The model found no new topics. Run it again, or try a deeper setting.")
            payload = {"topics": topics, "pages_used": len(titles), "searches_used": len(searches)}
        payload["page_read"] = read_ok
        row.payload = payload
        row.cost_usd, row.status = Decimal(str(llm.cost(row.depth, t_in, t_out))), "done"
        db.commit()
    except Exception as exc:  # noqa: BLE001 - the failure is the result; the screen shows it
        db.rollback()
        row = db.get(ContentModelRun, run_id)
        if row is not None:
            logger.exception("Content draft failed")
            row.status, row.error = "failed", str(exc)[:500]
            db.commit()
    finally:
        db.close()


def set_aside_topic(db: Session, client: Client, label: str, who: str, restore: bool = False) -> None:
    q = db.query(ContentState).filter(ContentState.client_id == client.id, ContentState.area == "topic", ContentState.key == label)
    if restore:
        q.delete()
    elif q.first() is None:
        db.add(ContentState(client_id=client.id, area="topic", key=label, created_by=who))
    db.commit()
