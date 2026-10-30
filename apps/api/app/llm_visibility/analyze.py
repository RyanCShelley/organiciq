"""Read an answer: is the brand named, is its site cited, who else is named, and in what order.

A port of llmviz's analyzer. Pure functions, no I/O. Names match as whole words, so a short pattern
such as "sma" never matches "small".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import httpx

from app.core.settings import get_settings
from app.llm_visibility.platforms import MAX_TOKENS  # noqa: F401  (kept next to the other limits)

EXTRACT_MODEL = "claude-haiku-4-5-20251001"
EXTRACT_MAX_CHARS = 6000


@dataclass
class BrandConfig:
    brand_name: str
    brand_patterns: list[str]
    domain: str
    #: (name, patterns) for each competitor.
    competitors: list[tuple[str, list[str]]] = field(default_factory=list)


@dataclass
class Analysis:
    brand_mentioned: bool = False
    url_cited: bool = False
    cited_urls: list[str] = field(default_factory=list)
    position: str = "Not mentioned"
    competitors_mentioned: list[str] = field(default_factory=list)
    all_brands_ordered: list[str] = field(default_factory=list)
    brand_rank: int = 0


def find_word(lower: str, pattern: str) -> int:
    """Where `pattern` first appears in `lower` as a whole word, or -1."""
    p = pattern.lower().strip()
    if not p:
        return -1
    match = re.search(rf"(?:^|[^a-z0-9]){re.escape(p)}(?=$|[^a-z0-9])", lower)
    if match is None:
        return -1
    return match.end() - len(p)


def analyze(text: str, citations: list[str], config: BrandConfig) -> Analysis:
    lower = text.lower()
    result = Analysis()
    positions: list[tuple[int, str, bool]] = []

    self_first = None
    for pattern in config.brand_patterns:
        at = find_word(lower, pattern)
        if at != -1:
            result.brand_mentioned = True
            self_first = at if self_first is None else min(self_first, at)
    if result.brand_mentioned and self_first is not None:
        positions.append((self_first, config.brand_name, True))
        share = self_first / len(lower) if lower else 0
        result.position = (
            "1st mention (top)" if share < 0.15 else "Early (top third)" if share < 0.4 else "Middle" if share < 0.7 else "Late (bottom third)"
        )

    for name, patterns in config.competitors:
        found = [at for at in (find_word(lower, p) for p in patterns) if at != -1]
        if found:
            result.competitors_mentioned.append(name)
            positions.append((min(found), name, False))

    positions.sort(key=lambda item: item[0])
    result.all_brands_ordered = [name for _, name, _ in positions]
    for rank, (_, _, is_self) in enumerate(positions, start=1):
        if is_self:
            result.brand_rank = rank
            break

    domain = config.domain.lower().strip()
    if domain and domain in lower:
        result.url_cited = True
        found_urls = re.findall(rf"https?://[^\s)\]]*{re.escape(domain)}[^\s)\]]*", text, flags=re.IGNORECASE)
        result.cited_urls = found_urls or [domain]

    if domain:
        for index, cited in enumerate(citations):
            if domain in str(cited).lower():
                result.url_cited = True
                if cited not in result.cited_urls:
                    result.cited_urls.append(cited)
                result.position = f"Source #{index + 1} of {len(citations)}"
    return result


def names_brand(prompt: str, config: BrandConfig) -> bool:
    """Whether the question itself says the brand's name, so an answer repeating it shows nothing."""
    lower = prompt.lower()
    return any(find_word(lower, p) != -1 for p in config.brand_patterns)


def visibility_type(a: Analysis, asked_by_name: bool = False) -> str:
    """How visible the brand was. When the prompt named it, only a citation of its site counts."""
    if asked_by_name:
        return "Cited" if a.url_cited else "Named in prompt"
    if a.url_cited and a.brand_mentioned:
        return "Cited + Mentioned"
    if a.url_cited:
        return "Cited"
    if a.brand_mentioned:
        return "Mentioned"
    return "Not visible"


_EXTRACT_SYSTEM = (
    "You extract brand/company/product names that appear in an LLM response. You return ONLY valid JSON, no prose.\n\n"
    'Rules:\n- Output JSON of shape: {"brands": ["…","…"]}\n'
    '- Include named companies, products, and platforms\n'
    '- EXCLUDE any name listed under "ALREADY TRACKED"\n'
    '- EXCLUDE generic terms ("the company", "an agency")\n'
    '- EXCLUDE technologies that are not proprietary brands\n'
    '- If nothing new is mentioned, return {"brands": []}.'
)


def extract_other_brands(text: str, known: list[str]) -> list[str]:
    """Brand names in an answer that are not already tracked. Best effort: any failure returns []."""
    key = get_settings().anthropic_api_key.strip()
    if not key or not text.strip():
        return []
    prompt = (
        f"ALREADY TRACKED (exclude these from your output): {', '.join(known) or '(none)'}\n\n"
        f"RESPONSE TEXT:\n{text[:EXTRACT_MAX_CHARS]}\n\nReturn JSON: " + '{"brands": ["…"]}'
    )
    try:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            json={
                "model": EXTRACT_MODEL,
                "max_tokens": 512,
                "temperature": 0,
                "system": _EXTRACT_SYSTEM,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        raw = "".join(b.get("text", "") for b in response.json().get("content", []) if b.get("type") == "text").strip()
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE)
        brands = json.loads(fenced.group(1).strip() if fenced else raw).get("brands", [])
    except Exception:  # noqa: BLE001
        return []
    excluded = {k.lower() for k in known}
    seen: set[str] = set()
    out: list[str] = []
    for brand in brands if isinstance(brands, list) else []:
        name = str(brand).strip()
        if name and name.lower() not in excluded and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out[:30]
