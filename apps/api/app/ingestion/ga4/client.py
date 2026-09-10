from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from app.ingestion.google_http import post_json, request_with_retry

ACCOUNT_SUMMARIES_URL = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"
RUN_REPORT_URL = "https://analyticsdata.googleapis.com/v1beta/{property}:runReport"


def list_ga4_properties(access_token: str) -> list[dict[str, str]]:
    properties: list[dict[str, str]] = []
    page_token: str | None = None
    with httpx.Client(timeout=60.0) as client:
        while True:
            params: dict[str, Any] = {"pageSize": 200}
            if page_token:
                params["pageToken"] = page_token
            res = request_with_retry(
                lambda: client.get(
                    ACCOUNT_SUMMARIES_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                ),
                description="GA4 accountSummaries.list",
            )
            data = res.json()
            for account in data.get("accountSummaries") or []:
                account_name = account.get("displayName") or ""
                for prop in account.get("propertySummaries") or []:
                    property_id = prop.get("property") or ""
                    if not property_id:
                        continue
                    properties.append(
                        {
                            "property_id": property_id,
                            "display_name": prop.get("displayName") or property_id,
                            "account_name": account_name,
                        }
                    )
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    return properties


def run_report(
    *,
    access_token: str,
    property_id: str,
    start_date: date,
    end_date: date,
    dimensions: list[str],
    metrics: list[str],
    limit: int = 100000,
) -> list[dict[str, Any]]:
    prop = property_id if property_id.startswith("properties/") else f"properties/{property_id}"
    url = RUN_REPORT_URL.format(property=prop)
    rows: list[dict[str, Any]] = []
    offset = 0

    with httpx.Client(timeout=120.0) as client:
        while True:
            body = {
                "dateRanges": [
                    {"startDate": start_date.isoformat(), "endDate": end_date.isoformat()}
                ],
                "dimensions": [{"name": d} for d in dimensions],
                "metrics": [{"name": m} for m in metrics],
                "limit": str(limit),
                "offset": str(offset),
            }
            res = post_json(
                client,
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
                description=f"GA4 runReport offset={offset}",
            )
            data = res.json()
            batch = list(data.get("rows") or [])
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < limit:
                break
            offset += len(batch)
    return rows
