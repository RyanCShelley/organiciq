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


def list_site_audits(
    *,
    api_key: str,
    limit: int = 100,
    offset: int = 0,
    search: str | None = None,
    date_start: date | None = None,
    date_end: date | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if search:
        params["search"] = search
    if date_start is not None:
        params["date_start"] = date_start.isoformat()
    if date_end is not None:
        params["date_end"] = date_end.isoformat()
    data = _request(api_key=api_key, method="GET", path="/site-audit/audits", params=params)
    return data if isinstance(data, dict) else {"items": [], "total": 0}


def get_audit_status(*, api_key: str, audit_id: int | str) -> dict[str, Any]:
    data = _request(
        api_key=api_key,
        method="GET",
        path="/site-audit/audits/status",
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
            path="/site-audit/audits/pages",
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
