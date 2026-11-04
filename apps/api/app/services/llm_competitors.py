"""Brands the AI answers name that the client has not listed as competitors.

A run already records, for each answer, the brands it named beyond the client's own and its listed competitors
(`other_brands_mentioned`). Counting them across the latest run shows who the AI platforms put in front of the client's
customers. A brand has no website in the answer, so its domain is read from the sources the answers cite: the one
whose name contains the brand's.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.llm_visibility import LlmResponse, LlmRun
from app.services.competitors import bare_domain

MAX_SHOWN = 15
MIN_TOKEN = 4


def _token(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def seen_in_answers(db: Session, client: Client, listed_names: set[str]) -> dict:
    """The brands named in the client's latest run, most mentioned first, with the platforms and a likely website."""
    run = db.query(LlmRun).filter(LlmRun.client_id == client.id).order_by(LlmRun.started_at.desc()).first()
    if run is None:
        return {"run_date": None, "brands": []}
    skip = {_token(n) for n in listed_names}
    mentions: Counter[str] = Counter()
    names: dict[str, str] = {}
    platforms: dict[str, set[str]] = defaultdict(set)
    prompts: dict[str, set[str]] = defaultdict(set)
    domains: dict[str, Counter[str]] = defaultdict(Counter)
    rows = db.query(LlmResponse).filter(LlmResponse.run_id == run.id, LlmResponse.client_id == client.id)
    for row in rows:
        cited = {bare_domain(u) for u in row.cited_urls or [] if urlsplit(u).netloc}
        for brand in set(row.other_brands_mentioned or []):
            key = _token(brand)
            if not key or key in skip:
                continue
            mentions[key] += 1
            names.setdefault(key, brand)
            platforms[key].add(row.platform)
            prompts[key].add(row.query_text)
            if len(key) >= MIN_TOKEN:
                for domain in cited:
                    if key in _token(domain.split(".")[0]):
                        domains[key][domain] += 1
    own = bare_domain(client.domain)
    listed = {bare_domain(d) for d in client.competitor_domains or []}
    out = []
    for key, count in mentions.most_common(MAX_SHOWN):
        guess = next((d for d, _ in domains[key].most_common() if d != own and d not in listed), None)
        out.append({"brand": names[key], "mentions": count, "platforms": sorted(platforms[key]), "prompts": len(prompts[key]), "domain": guess})
    return {"run_date": run.started_at.date().isoformat() if run.started_at else None, "brands": out}
