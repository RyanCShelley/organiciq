"""Suggest the questions to put to the AI platforms, from what the client actually sells.

Two groups, matching the ones already used: "Brand check" (names the brand, asks about a real product or against a
named competitor) and "Niche categories" (what a customer asks before they know the brand). The model proposes; the
checks here decide what is kept, so a "brand check" that forgets the brand, or a "niche" question that gives the
brand away, never reaches the list. Nothing is saved: the person ticks what to add.
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.llm_visibility import platforms, runner
from app.models.client import Client
from app.models.crawl import FactCrawlPageSnapshot
from app.models.llm_visibility import ClientLlmSettings
from app.models.watchlist import WatchlistBucket, WatchlistKeyword

BRAND_GROUP = "Brand check"
NICHE_GROUP = "Niche categories"
WANTED = 6
MAX_LENGTH = 220
#: Prefer the platform whose answers are cheapest and steadiest for writing; fall back to any with a key.
PREFERRED = ("anthropic", "openai", "gemini")


class SuggestError(Exception):
    """Nothing could be suggested; the message says why in words for the person using the tool."""


def _pages(db: Session, client: Client, limit: int = 40) -> list[str]:
    rows = (
        db.query(FactCrawlPageSnapshot.normalized_url, FactCrawlPageSnapshot.title)
        .filter(FactCrawlPageSnapshot.client_id == client.id, FactCrawlPageSnapshot.indexable.is_(True), FactCrawlPageSnapshot.status_code == 200)
        .filter(FactCrawlPageSnapshot.title.isnot(None))
        .order_by(FactCrawlPageSnapshot.inbound_editorial_links.desc(), FactCrawlPageSnapshot.inbound_internal_links.desc())
        .limit(limit)
        .all()
    )
    return [f"{title.strip()} ({url})" for url, title in rows if title and title.strip()]


def _watchlist(db: Session, client: Client, limit: int = 30) -> list[str]:
    rows = (
        db.query(WatchlistKeyword.keyword, WatchlistBucket.name)
        .join(WatchlistBucket, WatchlistBucket.id == WatchlistKeyword.bucket_id)
        .filter(WatchlistKeyword.client_id == client.id)
        .order_by(WatchlistBucket.sort_order, WatchlistKeyword.keyword)
        .limit(limit)
        .all()
    )
    return [f"{kw} ({bucket})" for kw, bucket in rows]


def build_request(db: Session, client: Client, settings: ClientLlmSettings, existing: list[str]) -> str:
    competitors = [c["name"] for c in (settings.competitors or {}).values()]
    pages = _pages(db, client)
    watch = _watchlist(db, client)
    return (
        f"You write questions that a real shopper would type into an AI assistant such as ChatGPT. They are used to test whether "
        f"the assistant mentions or cites the brand {settings.brand_name} ({client.domain}).\n\n"
        f"Competitors: {', '.join(competitors) or 'none listed'}.\n"
        f"Terms the brand is tracked for (with their topic):\n- " + "\n- ".join(watch or ["none yet"]) + "\n"
        f"Pages on the site (title and address):\n- " + "\n- ".join(pages or ["none crawled yet"]) + "\n\n"
        f"Write {WANTED} questions of each kind. Plain words, one sentence, under {MAX_LENGTH} characters, no numbering.\n"
        f'1. "brand_check": each names "{settings.brand_name}" exactly and asks about one real product or category from the pages above '
        f"(is it good, what do people say, who is it for), or compares it with one of the competitors listed. Use only products the pages show.\n"
        f'2. "niche": a customer asking what to buy in a category the site sells in, before knowing any brand. Never name '
        f"{settings.brand_name} or any competitor.\n"
        f"Do not repeat or lightly reword any of these, already asked:\n- " + "\n- ".join(existing or ["none"]) + "\n\n"
        'Answer with JSON only, exactly: {"brand_check": ["..."], "niche": ["..."]}'
    )


def _parse(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise SuggestError("The model's answer was not in the expected form. Try again.")
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise SuggestError("The model's answer was not in the expected form. Try again.") from exc


def keep(items: Any, *, must_name: list[str] | None, must_not_name: list[str], asked: set[str]) -> list[str]:
    """Drop what breaks the group's rule, repeats an existing question, or is not a usable sentence."""
    out: list[str] = []
    for raw in items if isinstance(items, list) else []:
        text = runner.clean_prompt(raw if isinstance(raw, str) else "")
        low = text.lower()
        if len(text) < 12 or len(text) > MAX_LENGTH or low in asked:
            continue
        if must_name is not None and not any(n in low for n in must_name):
            continue
        if any(n in low for n in must_not_name):
            continue
        asked.add(low)
        out.append(text)
    return out[:WANTED]


def suggest(db: Session, client: Client, settings: ClientLlmSettings) -> dict[str, Any]:
    existing = [p["prompt"] for p in runner.prompts_for(db, client)]
    platform = next((p for p in PREFERRED if platforms.api_key(p)), None)
    if platform is None:
        raise SuggestError("No AI platform has an API key on this install, so nothing can write the questions.")
    try:
        answer = platforms.ask(platform, build_request(db, client, settings, existing))
    except platforms.PlatformError as exc:
        raise SuggestError(f"The model did not answer: {exc}") from exc
    data = _parse(answer.text)

    brand = [settings.brand_name.lower(), *[p.lower() for p in (settings.brand_patterns or [])]]
    competitors = [n.lower() for c in (settings.competitors or {}).values() for n in [c["name"], *c.get("patterns", [])]]
    asked = {e.lower() for e in existing}
    brand_q = keep(data.get("brand_check"), must_name=brand, must_not_name=[], asked=asked)
    niche_q = keep(data.get("niche"), must_name=None, must_not_name=brand + competitors, asked=asked)
    return {
        "platform": platform,
        "groups": [
            {"topic_cluster": BRAND_GROUP, "prompts": brand_q},
            {"topic_cluster": NICHE_GROUP, "prompts": niche_q},
        ],
    }
