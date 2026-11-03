"""Wikidata concept lookup for the entity-bridge step of the schema audit.

Calls the public Wikidata search API (wbsearchentities). Free, no auth, but
Wikidata's terms of use require an identifying ``User-Agent`` header —
requests with the default ``python-httpx/x.y.z`` get throttled or refused.

Returns the top-K candidates per concept name so the analyst can pick the
right entity before it lands in the generated JSON-LD as a sameAs link.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

import logging

log = logging.getLogger("organiciq.schema_tools.wikidata")

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
DEFAULT_TIMEOUT = 10.0
DEFAULT_LIMIT = 3
MAX_RETRIES = 3

# Wikidata's user-agent policy requires an identifying string. Without it,
# requests are throttled or rejected silently — which is what produced the
# "No Wikidata candidates found" symptom in production.
# https://meta.wikimedia.org/wiki/User-Agent_policy
WIKIDATA_HEADERS = {
    "User-Agent": (
        "OrganicIQ-SchemaTools/1.0 "
        "(https://github.com/RyanCShelley/organiciq; ryan@smamarketing.net)"
    ),
}


@dataclass
class QIDCandidate:
    """One Wikidata search result."""

    qid: str
    label: str
    description: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "qid": self.qid,
            "label": self.label,
            "description": self.description,
            "url": self.url,
        }


async def search_concept(
    concept: str,
    *,
    limit: int = DEFAULT_LIMIT,
    client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[QIDCandidate]:
    """Search Wikidata for *concept* and return top-K candidates.

    Retries up to MAX_RETRIES times on transient errors (429, 5xx, network).
    Returns ``[]`` only after retries are exhausted, and logs at warning
    level so silent failures are diagnosable in production.
    """
    params = {
        "action": "wbsearchentities",
        "search": concept,
        "language": "en",
        "format": "json",
        "limit": str(limit),
        "type": "item",
    }

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout, headers=WIKIDATA_HEADERS)

    assert client is not None

    last_err: Exception | None = None
    try:
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.get(
                    WIKIDATA_API,
                    params=params,
                    headers=WIKIDATA_HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
                break  # success
            except (httpx.HTTPError, ValueError) as exc:
                last_err = exc
                if attempt < MAX_RETRIES - 1:
                    backoff = 2**attempt
                    log.warning("wikidata.retry %s", dict(concept=concept,
                        attempt=attempt + 1,
                        backoff_s=backoff,
                        error=str(exc)),
                    )
                    await asyncio.sleep(backoff)
                else:
                    log.error("wikidata.exhausted %s", dict(concept=concept,
                        attempts=MAX_RETRIES,
                        error=str(exc)),
                    )
                    return []
        else:
            return []  # all retries failed
    finally:
        if own_client:
            await client.aclose()

    if last_err and "data" not in locals():
        return []

    raw = data.get("search") or []
    out: list[QIDCandidate] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("id") or "").strip()
        if not qid.startswith("Q"):
            continue
        out.append(
            QIDCandidate(
                qid=qid,
                label=str(item.get("label") or qid),
                description=str(item.get("description") or ""),
                url=f"https://www.wikidata.org/wiki/{qid}",
            )
        )
    if not out:
        log.info("wikidata.no_match %s", dict(concept=concept, raw_count=len(raw)))
    return out


async def search_many(
    concepts: list[str],
    *,
    limit: int = DEFAULT_LIMIT,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, list[QIDCandidate]]:
    """Concurrent lookup for a list of concept names.

    Empty / duplicate names are skipped. The returned dict is keyed by the
    *original* concept string (preserving case) so callers can match back.
    """
    cleaned = [c.strip() for c in concepts if c and c.strip()]
    # Dedup while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for c in cleaned:
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    if not unique:
        return {}

    async with httpx.AsyncClient(timeout=timeout, headers=WIKIDATA_HEADERS) as client:
        tasks = [search_concept(c, limit=limit, client=client) for c in unique]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    return dict(zip(unique, results, strict=True))
