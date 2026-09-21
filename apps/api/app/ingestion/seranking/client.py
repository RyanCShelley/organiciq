from __future__ import annotations

import time
from datetime import date
from typing import Any

import httpx

BASE_URL = "https://api.seranking.com/v1"
# SE Ranking allows ≤5 requests/second; stay under with a small margin.
_MIN_INTERVAL_SECONDS = 0.22
_last_request_at = 0.0


def _throttle() -> None:
    global _last_request_at
    now = time.monotonic()
    wait = _MIN_INTERVAL_SECONDS - (now - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Token {api_key}",
        "Accept": "application/json",
    }


def _request(
    *,
    api_key: str,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    retries: int = 3,
) -> Any:
    url = f"{BASE_URL}{path}"
    last_error: Exception | None = None
    for attempt in range(retries):
        _throttle()
        try:
            with httpx.Client(timeout=120.0, trust_env=False) as client:
                res = client.request(method, url, headers=_headers(api_key), params=params or {})
            if res.status_code == 429:
                time.sleep(1.0 * (attempt + 1))
                continue
            res.raise_for_status()
            if res.status_code == 204 or not res.content:
                return None
            return res.json()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt + 1 >= retries:
                break
            time.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def list_sites(api_key: str) -> list[dict[str, Any]]:
    data = _request(api_key=api_key, method="GET", path="/project-management/sites")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.get("sites") or data.get("data") or [])
    return []


def list_search_engines(api_key: str, site_id: str | int) -> list[dict[str, Any]]:
    data = _request(
        api_key=api_key,
        method="GET",
        path="/project-management/sites/search-engines",
        params={"site_id": site_id},
    )
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.get("search_engines") or data.get("data") or [])
    return []


def list_keywords(api_key: str, site_id: str | int, site_engine_id: str | int | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"site_id": site_id}
    if site_engine_id is not None:
        params["site_engine_id"] = site_engine_id
    data = _request(api_key=api_key, method="GET", path="/project-management/keywords", params=params)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.get("keywords") or data.get("data") or [])
    return []


def list_keyword_groups(api_key: str, site_id: str | int) -> list[dict[str, Any]]:
    data = _request(
        api_key=api_key,
        method="GET",
        path="/project-management/keywords/groups",
        params={"site_id": site_id},
    )
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.get("groups") or data.get("data") or [])
    return []


def list_positions(
    *,
    api_key: str,
    site_id: str | int,
    date_from: date,
    date_to: date,
    site_engine_id: str | int | None = None,
    with_landing_pages: int = 1,
    with_serp_features: int = 1,
) -> Any:
    params: dict[str, Any] = {
        "site_id": site_id,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "with_landing_pages": with_landing_pages,
        "with_serp_features": with_serp_features,
    }
    if site_engine_id is not None:
        params["site_engine_id"] = site_engine_id
    return _request(
        api_key=api_key,
        method="GET",
        path="/project-management/sites/positions",
        params=params,
    )


def site_summary(api_key: str, site_id: str | int) -> dict[str, Any]:
    data = _request(
        api_key=api_key,
        method="GET",
        path="/project-management/sites/summary",
        params={"site_id": site_id},
    )
    return data if isinstance(data, dict) else {}


def list_competitors(api_key: str, site_id: str | int) -> list[dict[str, Any]]:
    data = _request(
        api_key=api_key,
        method="GET",
        path="/project-management/competitors",
        params={"site_id": site_id},
    )
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.get("competitors") or data.get("data") or [])
    return []


def competitor_metrics(
    *,
    api_key: str,
    site_id: str | int,
    metric_date: date,
    site_engine_id: str | int,
) -> Any:
    return _request(
        api_key=api_key,
        method="GET",
        path="/project-management/competitors/metrics",
        params={
            "site_id": site_id,
            "date": metric_date.isoformat(),
            "site_engine_id": site_engine_id,
        },
    )


def get_airt_llm_statistics(
    *,
    api_key: str,
    site_id: str | int,
    llm_id: str | int,
    date_from: date,
    date_to: date,
    top: int = 0,
) -> dict[str, Any]:
    data = _request(
        api_key=api_key,
        method="GET",
        path="/project-management/airt/llm/statistics",
        params={
            "site_id": site_id,
            "llm_id": llm_id,
            "from": date_from.isoformat(),
            "to": date_to.isoformat(),
            "top": top,
        },
    )
    return data if isinstance(data, dict) else {}


def list_airt_llm_engines(api_key: str, site_id: str | int) -> list[dict[str, Any]]:
    data = _request(
        api_key=api_key,
        method="GET",
        path="/project-management/airt/llm",
        params={"site_id": site_id},
    )
    return data if isinstance(data, list) else []


def list_airt_prompt_groups(api_key: str, site_id: str | int) -> list[dict[str, Any]]:
    data = _request(
        api_key=api_key,
        method="GET",
        path="/project-management/airt/prompts/groups",
        params={"site_id": site_id},
    )
    return data if isinstance(data, list) else []


def list_airt_prompts_paginated(
    *,
    api_key: str,
    site_id: str | int,
    llm_id: str | int,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = _request(
            api_key=api_key,
            method="GET",
            path="/project-management/airt/prompts",
            params={
                "site_id": site_id,
                "llm_id": llm_id,
                "limit": page_size,
                "offset": offset,
            },
        )
        if not isinstance(data, dict):
            break
        batch = data.get("items") or []
        if not isinstance(batch, list):
            break
        rows.extend(item for item in batch if isinstance(item, dict))
        total = int(data.get("total") or 0)
        offset += len(batch)
        if offset >= total or not batch:
            break
    return rows


def get_audit_status(*, api_key: str, audit_id: int | str) -> dict[str, Any]:
    """Crawl state for a project's audit. `audit_id` is the SE Ranking project id."""
    data = _request(
        api_key=api_key,
        method="GET",
        path="/project-management/audits/status",
        params={"audit_id": audit_id},
    )
    return data if isinstance(data, dict) else {}


def get_audit_report(*, api_key: str, audit_id: int | str) -> dict[str, Any]:
    """Section-by-section audit report, including the health score."""
    data = _request(
        api_key=api_key,
        method="GET",
        path="/project-management/audits/report",
        params={"audit_id": audit_id},
    )
    return data if isinstance(data, dict) else {}


def list_audit_pages_paginated(
    *,
    api_key: str,
    audit_id: int | str,
    page_size: int = 100,
    max_requests: int = 2000,
    max_seconds: float = 20 * 60,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    requests_made = 0
    started = time.monotonic()
    while True:
        if requests_made >= max_requests:
            raise RuntimeError(
                f"SE Ranking audit {audit_id} page fetch exceeded {max_requests} requests "
                f"({len(rows)} pages staged)"
            )
        if time.monotonic() - started > max_seconds:
            raise RuntimeError(
                f"SE Ranking audit {audit_id} page fetch timed out after {int(max_seconds)}s "
                f"({len(rows)} pages staged)"
            )
        data = _request(
            api_key=api_key,
            method="GET",
            path="/project-management/audits/pages",
            params={"audit_id": audit_id, "limit": page_size, "offset": offset},
        )
        requests_made += 1
        if not isinstance(data, dict):
            break
        batch = data.get("items") or []
        if not isinstance(batch, list):
            break
        rows.extend(item for item in batch if isinstance(item, dict))
        total = int(data.get("total") or 0)
        offset += len(batch)
        if offset >= total or not batch:
            break
    return rows


# Curated Website Audit issue codes used by Decision Engine Technical SEO.
AUDIT_ISSUE_CODES: tuple[str, ...] = (
    "redirect45xx",
    "redirect_chain",
    "title_missing",
    "description_missing",
    "title_duplicate",
    "description_duplicate",
    "sitemap_missing",
    "no_robots",
    "robots_not_accessible",
    "robots_has_errors",
    "robots_disallow_crawling",
)

SITE_LEVEL_ISSUE_CODES: frozenset[str] = frozenset(
    {
        "sitemap_missing",
        "no_robots",
        "robots_not_accessible",
        "robots_has_errors",
        "robots_disallow_crawling",
    }
)


def list_issue_pages_paginated(
    *,
    api_key: str,
    audit_id: int | str,
    code: str,
    page_size: int = 100,
    max_requests: int = 500,
    max_seconds: float = 5 * 60,
) -> list[dict[str, Any]]:
    """Return pages (or site markers) affected by a Website Audit issue code."""
    rows: list[dict[str, Any]] = []
    offset = 0
    requests_made = 0
    started = time.monotonic()
    while True:
        if requests_made >= max_requests:
            raise RuntimeError(
                f"SE Ranking audit {audit_id} issue {code} fetch exceeded {max_requests} requests"
            )
        if time.monotonic() - started > max_seconds:
            raise RuntimeError(
                f"SE Ranking audit {audit_id} issue {code} fetch timed out after {int(max_seconds)}s"
            )
        data = _request(
            api_key=api_key,
            method="GET",
            path="/project-management/audits/issue-pages",
            params={
                "audit_id": audit_id,
                "code": code,
                "limit": page_size,
                "offset": offset,
            },
        )
        requests_made += 1
        if data is None:
            break
        if isinstance(data, list):
            batch = [item for item in data if isinstance(item, dict)]
            rows.extend(batch)
            break
        if not isinstance(data, dict):
            break
        batch = data.get("urls")
        if batch is None:
            batch = data.get("items") or data.get("pages") or []
        if not isinstance(batch, list):
            break
        # `urls_type: simple_urls_array` means bare URL strings, not objects.
        rows.extend(
            {"url": item} if isinstance(item, str) else item
            for item in batch
            if isinstance(item, (str, dict))
        )
        total = int(data.get("total_urls") or data.get("total") or 0)
        offset += len(batch)
        if offset >= total or not batch:
            break
    return rows


def list_airt_prompt_rankings_paginated(
    *,
    api_key: str,
    site_id: str | int,
    llm_id: str | int,
    date_from: date,
    date_to: date,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = _request(
            api_key=api_key,
            method="GET",
            path="/project-management/airt/prompts/rankings",
            params={
                "site_id": site_id,
                "llm_id": llm_id,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "limit": page_size,
                "offset": offset,
            },
        )
        if not isinstance(data, dict):
            break
        batch = data.get("items") or []
        if not isinstance(batch, list):
            break
        rows.extend(item for item in batch if isinstance(item, dict))
        total = int(data.get("total") or 0)
        offset += len(batch)
        if offset >= total or not batch:
            break
    return rows


# --- Domain Analysis (Data API) ---------------------------------------------
#
# Same host and Token auth as project-management, but metered in credits rather
# than rate-limited: /domain/keywords costs 100 credits PER REQUEST, so each
# extra page is another 100. One page at the maximum limit, ordered by volume,
# buys the 1000 most valuable keywords for a flat 100 credits — which is why
# this deliberately does not paginate.
DOMAIN_KEYWORDS_CREDITS_PER_REQUEST = 100
DOMAIN_KEYWORDS_MAX_LIMIT = 1000


def list_domain_keywords(
    *,
    api_key: str,
    domain: str,
    source: str = "us",
    limit: int = DOMAIN_KEYWORDS_MAX_LIMIT,
    order_field: str = "volume",
    order_type: str = "desc",
) -> list[dict[str, Any]]:
    """
    Organic keywords the domain ranks for, highest volume first.

    Single request by design — see the credit note above. The response is a
    bare JSON array.
    """
    data = _request(
        api_key=api_key,
        method="GET",
        path="/domain/keywords",
        params={
            "domain": domain,
            "source": source,
            "type": "organic",
            "limit": min(int(limit), DOMAIN_KEYWORDS_MAX_LIMIT),
            "page": 1,
            "order_field": order_field,
            "order_type": order_type,
        },
    )
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    # Defensive: docs describe a bare array, but tolerate a wrapper.
    if isinstance(data, dict):
        for key in ("keywords", "data", "items"):
            rows = data.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


# --- AI Search (Data API) ---------------------------------------------------
#
# prompts-by-target is priced PER RETURNED PROMPT, not per request — 200 credits
# each. The API's own default limit of 100 therefore costs 20,000 credits for a
# single engine, which is 200x the whole domain-keywords lookup. Everything here
# is built to make that cost explicit and bounded rather than incidental.
AI_SEARCH_CREDITS_PER_PROMPT = 200
AI_SEARCH_DEFAULT_LIMIT = 5
# Absolute ceiling, regardless of any per-client setting. Not the API's 1000:
# at 200 credits each that would be 200,000 credits in one call.
AI_SEARCH_MAX_LIMIT = 50
# Applied when a client has no explicit ai_search_prompt_limit.
AI_SEARCH_DEFAULT_CLIENT_LIMIT = 5

AI_SEARCH_DEFAULT_ENGINE = "chatgpt"

AI_SEARCH_ENGINES: tuple[str, ...] = (
    "chatgpt",
    "perplexity",
    "gemini",
    "ai-overview",
    "ai-mode",
)


def ai_search_credit_cost(limit: int) -> int:
    """Credits a run of this size will cost. Shown before anyone spends it."""
    return max(0, int(limit)) * AI_SEARCH_CREDITS_PER_PROMPT


def ai_search_limit_for(client_limit: int | None) -> int:
    """
    Effective ceiling for a client: their setting, bounded by the global cap.

    A per-client value is how a few high-value accounts get more prompts
    without raising the floor for everyone.
    """
    requested = client_limit if client_limit else AI_SEARCH_DEFAULT_CLIENT_LIMIT
    return max(1, min(int(requested), AI_SEARCH_MAX_LIMIT))


def list_ai_search_prompts_by_target(
    *,
    api_key: str,
    target: str,
    engine: str,
    source: str = "us",
    limit: int = AI_SEARCH_DEFAULT_LIMIT,
    scope: str = "base_domain",
) -> dict[str, Any]:
    """
    Prompts where `target` appears in AI answers, highest volume first.

    One engine per request — the API takes a single `engine`. Never paginated:
    every extra row is another 200 credits.
    """
    if engine not in AI_SEARCH_ENGINES:
        raise ValueError(f"Unsupported AI engine: {engine}")

    capped = max(1, min(int(limit), AI_SEARCH_MAX_LIMIT))
    data = _request(
        api_key=api_key,
        method="GET",
        path="/ai-search/prompts-by-target",
        params={
            "target": target,
            "engine": engine,
            "source": source,
            "scope": scope,
            "limit": capped,
            "offset": 0,
            "sort": "volume",
            "sort_order": "desc",
        },
    )
    if not isinstance(data, dict):
        return {"total": 0, "date": None, "prompts": []}
    prompts = data.get("prompts")
    return {
        "total": int(data.get("total") or 0),
        "date": data.get("date"),
        "prompts": [p for p in prompts if isinstance(p, dict)] if isinstance(prompts, list) else [],
    }
