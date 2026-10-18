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


class ReportRows(list):
    """Rows plus provider evidence that the requested report was fully read."""
    def __init__(self):
        super().__init__()
        self.pages = []
        self.complete = False


def run_report(
    *,
    access_token: str,
    property_id: str,
    start_date: date,
    end_date: date,
    dimensions: list[str],
    metrics: list[str],
    limit: int = 100000,
    dimension_filter: dict[str, Any] | None = None,
    timeout_seconds: float = 120.0,
    max_attempts: int | None = None,
) -> list[dict[str, Any]]:
    prop = property_id if property_id.startswith("properties/") else f"properties/{property_id}"
    url = RUN_REPORT_URL.format(property=prop)
    rows = ReportRows()
    offset = 0
    expected_count = None
    seen = set()

    with httpx.Client(timeout=timeout_seconds) as client:
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
            if dimension_filter is not None:
                body["dimensionFilter"] = dimension_filter
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
            description = f"GA4 runReport offset={offset}"
            if max_attempts is None:
                res = post_json(client, url, headers=headers, json=body, description=description)
            else:
                res = request_with_retry(lambda: client.post(url, headers=headers, json=body),
                    description=description, max_attempts=max_attempts)
            data = res.json()
            metadata = data.get("metadata") or {}
            rows.pages.append({"row_count": data.get("rowCount"), "metadata": metadata})
            if metadata.get("dataLossFromOtherRow") or metadata.get("subjectToThresholding") or metadata.get("samplingMetadatas"):
                raise RuntimeError("GA4 report is subject to sampling, thresholding or aggregation loss; a complete replacement could not be verified")
            count = data.get("rowCount")
            # Protobuf JSON may omit scalar defaults. An empty successful report
            # with the exact requested headers establishes a zero row count;
            # an empty/malformed body alone does not.
            if (
                count is None and not data.get("rows") and offset == 0
                and [header.get("name") for header in data.get("dimensionHeaders", [])] == dimensions
                and [header.get("name") for header in data.get("metricHeaders", [])] == metrics
                and metrics
            ):
                count = 0
            if not isinstance(count, int) or count < 0:
                raise RuntimeError("GA4 report omitted its total row count; completeness could not be verified")
            if expected_count is not None and count != expected_count:
                raise RuntimeError("GA4 report row count changed during pagination; retry the extraction")
            expected_count = count
            batch = list(data.get("rows") or [])
            for row in batch:
                key = tuple(value.get("value") for value in row.get("dimensionValues", []))
                if key in seen:
                    raise RuntimeError("GA4 pagination returned duplicate dimension rows; retry the extraction")
                seen.add(key)
            rows.extend(batch)
            if len(rows) >= count:
                if len(rows) != count:
                    raise RuntimeError("GA4 report returned more rows than declared")
                rows.complete = True
                break
            if not batch:
                raise RuntimeError("GA4 report ended before all declared rows were returned")
            offset += len(batch)
    return rows
