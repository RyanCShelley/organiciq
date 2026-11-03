"""Ask the data: a question in plain words, answered by a Claude model that queries this client's tables.

The model gets one tool, `run_sql`, behind the read-only door in schema.py and sql.py. It loops (query, read, query again)
until it can answer, then writes the answer with the numbers and where each came from. Every question is logged with the
queries run and what it cost, and a client's month stops at a cap.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ask import schema, sql
from app.core.db import SessionLocal
from app.core.settings import get_settings
from app.models.ask_data import AskDataLog
from app.models.client import Client

logger = logging.getLogger("organiciq.ask")

#: depth -> (model, dollars per million input tokens, dollars per million output tokens)
DEPTHS: dict[str, tuple[str, float, float]] = {
    "quick": ("claude-sonnet-5-5", 2.0, 10.0),
    "deep": ("claude-opus-5-5", 4.0, 20.0),
    "deepest": ("claude-fable-5-1", 10.0, 50.0),
}
MAX_QUERIES = 8
MAX_TOKENS = 8000
TIMEOUT_SECONDS = 240.0
HISTORY_TURNS = 6
STALE_MINUTES = 8

TOOL = {
    "name": "run_sql",
    "description": "Run one read-only SQL SELECT against this client's tables (already limited to this client). Returns at most 40 rows, so aggregate in SQL. One statement, no comments.",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "A single SELECT (or WITH ... SELECT) statement."}}, "required": ["query"]},
}

NOTES = """How the data works:
- facts_ga4_traffic: one row per day, landing page, source/medium and channel. sessions, engaged_sessions, views, active_users. engagement_seconds is the engaged time summed over the sessions of the row (average time per visit = sum(engagement_seconds) / sum(sessions) over rows where engagement_seconds is not null; it is null on rows pulled before it was collected, so say so when it is missing). normalized_url is the landing page.
- facts_ga4_events: event_count per day, landing page, channel and event_name. A "conversion" or "key action" is only an event listed in conversion_definitions (active = true): join on event_name. Do not call add_to_cart or begin_checkout conversions unless asked.
- channel is one of: organic_search, ai_referral, direct_unattributed, paid_search, paid_social, display, cross_network, other_paid, referral, social, email, other.
- facts_gsc_daily: site totals per day from Search Console. facts_gsc_pages and facts_gsc_query_pages: clicks, impressions, average_position (weight by impressions when averaging) by page and by query+page. Search Console runs about 3 days behind.
- facts_ser_rankings: tracked keywords (SE Ranking): position 0 means not ranking in the top 100; volume is monthly searches. facts_ser_competitors and facts_ser_competitor_keywords: competitors' domains and what they rank for; either may be empty.
- facts_bing_query_stats: weekly Bing queries. facts_serp_features: search result features.
- facts_crawl_page_snapshots, facts_crawl_page_issues, facts_crawl_internal_links: the site crawl (latest snapshot_date is the current state).
- llm_runs / llm_responses: AI visibility runs. A response has query_text, platform, brand_mentioned, url_cited, competitors_mentioned, other_brands_mentioned (brands named that are not tracked), visibility_type. Rows with asked_by_name = true came from a question that named the brand: leave them out of discovery rates.
- annotations: the change log (dated changes and work shipped). engine_tasks: planned and shipped growth actions. watchlist_keywords / watchlist_buckets: the keywords the team tracks.
Rules: check max(date) of a table before comparing periods. Compare like with like (same number of days). Say when data is missing or thin instead of guessing; never invent a figure. Brand searches (queries containing the brand name) are navigation: never recommend work for them."""


def system_prompt(db: Session, client: Client, today: date) -> str:
    return (
        f"You answer a search marketer's questions about ONE client, {client.client_name} ({client.domain}), by querying a read-only PostgreSQL database with the run_sql tool. Today is {today.isoformat()}.\n\n"
        f"Tables (already limited to this client):\n{schema.table_notes(db)}\n\n{NOTES}\n\n"
        "How to answer: query first, then answer. Lead with the answer in one or two sentences, then the evidence: the numbers, the period, and which table each came from. "
        "Use short sections or a small table when it helps. If the question is ambiguous, pick the most reasonable reading, say which you used, and offer the other. "
        "Name what the data cannot tell (for example a measure that is not collected). Never mention SQL errors, row limits or internal rule codes to the reader; if a query fails, fix it and try again."
    )


def cost_usd(depth: str, input_tokens: int, output_tokens: int) -> Decimal:
    _, rate_in, rate_out = DEPTHS[depth]
    return Decimal(str(round(input_tokens / 1e6 * rate_in + output_tokens / 1e6 * rate_out, 4)))


def month_spend(db: Session, client_id: UUID, now: datetime | None = None) -> Decimal:
    now = now or datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return db.query(func.coalesce(func.sum(AskDataLog.cost_usd), 0)).filter(AskDataLog.client_id == client_id, AskDataLog.created_at >= start).scalar() or Decimal(0)


def _call(model: str, system: str, messages: list[dict]) -> dict[str, Any]:
    key = get_settings().anthropic_api_key.strip()
    if not key:
        raise RuntimeError("The Anthropic key is not set on this install, so questions cannot be answered.")
    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "anthropic-beta": "server-side-fallback-2026-07-01"},
        json={"model": model, "max_tokens": MAX_TOKENS, "system": system, "messages": messages, "tools": [TOOL], "tool_choice": {"type": "auto"}, "fallbacks": "default"},
        timeout=TIMEOUT_SECONDS,
    )
    if response.status_code >= 400:
        detail = ""
        try:
            detail = response.json().get("error", {}).get("message", "")
        except ValueError:
            pass
        raise RuntimeError(f"The model did not answer ({response.status_code}). {detail}"[:400])
    return response.json()


def answer(log_id: UUID, history: list[dict[str, str]]) -> None:
    """Work out one logged question. Runs in the background; progress is written to the log row so the screen can show it."""
    db = SessionLocal()
    try:
        log = db.get(AskDataLog, log_id)
        if log is None:
            return
        client = db.get(Client, log.client_id)
        model = DEPTHS[log.depth][0]
        system = system_prompt(db, client, date.today())
        messages: list[dict] = [{"role": m["role"], "content": m["content"]} for m in history[-HISTORY_TURNS:]]
        messages.append({"role": "user", "content": log.question})
        tin = tout = 0
        queries: list[dict] = []
        text = ""
        for turn in range(MAX_QUERIES + 2):
            reply = _call(model, system, messages)
            usage = reply.get("usage") or {}
            tin += int(usage.get("input_tokens") or 0)
            tout += int(usage.get("output_tokens") or 0)
            content = reply.get("content") or []
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
            stop = reply.get("stop_reason")
            if stop == "refusal":
                raise RuntimeError("The model declined to answer this one. Try asking it differently.")
            uses = [b for b in content if b.get("type") == "tool_use"]
            if stop != "tool_use" or not uses:
                break
            messages.append({"role": "assistant", "content": content})  # unchanged, thinking blocks included
            results = []
            for use in uses:
                if len(queries) >= MAX_QUERIES:
                    result = {"error": "No more queries are available. Answer now with what you have."}
                else:
                    result = sql.run(db, log.client_id, str((use.get("input") or {}).get("query") or ""))
                queries.append({"query": str((use.get("input") or {}).get("query") or "")[:1500], "rows": len(result.get("rows") or []), "error": result.get("error")})
                results.append({"type": "tool_result", "tool_use_id": use["id"], "content": json.dumps(result), **({"is_error": True} if result.get("error") else {})})
            messages.append({"role": "user", "content": results})
            log.queries, log.input_tokens, log.output_tokens = queries, tin, tout
            db.commit()
        log.queries, log.input_tokens, log.output_tokens = queries, tin, tout
        log.cost_usd = cost_usd(log.depth, tin, tout)
        log.answer = text or "The model did not write an answer. Try asking again."
        log.status, log.completed_at = "done", datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - the failure is the result; the screen shows it
        db.rollback()
        log = db.get(AskDataLog, log_id)
        if log is not None:
            logger.exception("Ask the data failed")
            log.status, log.error, log.completed_at = "failed", str(exc)[:600], datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
