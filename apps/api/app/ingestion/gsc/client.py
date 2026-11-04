from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any
from urllib.parse import quote

import httpx

from app.ingestion.google_http import get as http_get, post_json
from app.services.jobs import check_stop

SEARCH_ANALYTICS_URL = "https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
SITES_LIST_URL = "https://www.googleapis.com/webmasters/v3/sites"


def list_sites(access_token: str) -> list[dict[str, Any]]:
    with httpx.Client(timeout=60.0) as client:
        res = http_get(
            client,
            SITES_LIST_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            description="GSC sites.list",
        )
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
) -> Iterator[dict[str, Any]]:
    """Paginate Search Analytics until exhausted, yielding rows as each page arrives.

    A large property is millions of rows; holding them all as a list before saving any was the memory problem.
    """
    encoded_site = quote(site_url, safe="")
    url = SEARCH_ANALYTICS_URL.format(site=encoded_site)
    start_row = 0

    with httpx.Client(timeout=120.0) as client:
        while True:
            check_stop()
            body = {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "dimensions": dimensions,
                "rowLimit": row_limit,
                "startRow": start_row,
            }
            res = post_json(
                client,
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
                description=f"GSC searchAnalytics.query startRow={start_row}",
            )
            batch = list((res.json() or {}).get("rows") or [])
            if not batch:
                return
            yield from batch
            if len(batch) < row_limit:
                return
            start_row += len(batch)
