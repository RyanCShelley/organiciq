from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import quote

import httpx

from app.ingestion.google_auth import credentials_from_tokens, ensure_access_token

SEARCH_ANALYTICS_URL = "https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
SITES_LIST_URL = "https://www.googleapis.com/webmasters/v3/sites"


def list_sites(access_token: str) -> list[dict[str, Any]]:
    with httpx.Client(timeout=60.0) as client:
        res = client.get(
            SITES_LIST_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        res.raise_for_status()
        data = res.json()
    return list(data.get("siteEntry") or [])


def query_search_analytics(
    *,
    access_token: str,
    site_url: str,
    start_date: date,
    end_date: date,
    dimensions: list[str],
    row_limit: int = 25000,
) -> list[dict[str, Any]]:
    """Paginate Search Analytics until exhausted."""
    encoded_site = quote(site_url, safe="")
    url = SEARCH_ANALYTICS_URL.format(site=encoded_site)
    rows: list[dict[str, Any]] = []
    start_row = 0

    with httpx.Client(timeout=120.0) as client:
        while True:
            body = {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "dimensions": dimensions,
                "rowLimit": row_limit,
                "startRow": start_row,
            }
            res = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            res.raise_for_status()
            batch = list((res.json() or {}).get("rows") or [])
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < row_limit:
                break
            start_row += len(batch)

    return rows
