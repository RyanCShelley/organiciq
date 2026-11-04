"""What the AI platforms said to the prompt paired with a search, from the client's latest LLM visibility run.

Feeds the answer-injection suggestion: when a platform answered the question without citing the site,
the page may not hold a direct answer worth citing. Returns the facts, never a verdict.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.llm_visibility import LlmResponse, LlmRun
from app.models.watchlist import WatchlistKeyword


def _words(text: str) -> list[str]:
    return " ".join(text.lower().split()).split()


def paired_keyword(db: Session, client: Client, search: str) -> WatchlistKeyword | None:
    """The watchlist keyword with a paired prompt that this search is about: the longest one the search contains."""
    wanted = " ".join(search.lower().split())
    best = None
    for kw in db.query(WatchlistKeyword).filter(WatchlistKeyword.client_id == client.id):
        if not (kw.paired_ai_prompt or "").strip():
            continue
        key = " ".join(kw.keyword.lower().split())
        if key == wanted or f" {key} " in f" {wanted} ":
            if best is None or len(key) > len(" ".join(best.keyword.lower().split())):
                best = kw
    return best


def for_search(db: Session, client: Client, search: str) -> dict[str, Any]:
    """`{ok: True, ...}` with the platforms' answers, or `{ok: False, reason}` saying what is missing."""
    keyword = paired_keyword(db, client, search)
    if keyword is None:
        return {"ok": False, "reason": "No watchlist keyword with a paired AI prompt matches this search."}
    run = (
        db.query(LlmRun)
        .filter(LlmRun.client_id == client.id, LlmRun.status == "completed")
        .order_by(LlmRun.started_at.desc())
        .first()
    )
    if run is None:
        return {"ok": False, "reason": "No LLM visibility run has been done for this client yet."}
    prompt = " ".join(keyword.paired_ai_prompt.split())
    rows = [
        r
        for r in db.query(LlmResponse).filter(LlmResponse.run_id == run.id)
        if r.visibility_type != "Error" and " ".join(r.query_text.split()).lower() == prompt.lower()
    ]
    if not rows:
        return {"ok": False, "reason": "The latest run did not ask this keyword's paired prompt (it was added after that run)."}
    named = Counter(b for r in rows for b in (list(r.competitors_mentioned or []) + list(r.other_brands_mentioned or [])))
    return {
        "ok": True,
        "run_date": run.started_at.date().isoformat(),
        "prompt": prompt,
        "keyword": keyword.keyword,
        "platforms": [
            {"platform": r.platform, "cited": bool(r.url_cited), "mentioned": bool(r.brand_mentioned)}
            for r in sorted(rows, key=lambda r: r.platform)
        ],
        "named": [name for name, _ in named.most_common(5)],
    }
