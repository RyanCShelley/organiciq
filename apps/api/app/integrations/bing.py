"""Bing Webmaster Tools: which sites the workspace's API key can see."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

import httpx

SITES_URL = "https://ssl.bing.com/webmaster/api.svc/json/GetUserSites"
TIMEOUT_SECONDS = 20.0


class BingError(Exception):
    pass


def list_sites(api_key: str) -> list[dict]:
    """`[{"url": ..., "verified": bool}]` for every site on the key's account."""
    try:
        res = httpx.get(SITES_URL, params={"apikey": api_key}, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise BingError(f"Bing Webmaster did not answer: {exc}") from exc
    if res.status_code >= 400:
        raise BingError(f"Bing Webmaster refused the request ({res.status_code}). Check the API key.")
    try:
        rows = res.json().get("d") or []
    except ValueError as exc:
        raise BingError("Bing Webmaster sent something that was not JSON.") from exc
    return [
        {"url": str(row["Url"]), "verified": bool(row.get("IsVerified"))}
        for row in rows
        if row.get("Url")
    ]


QUERY_STATS_URL = "https://ssl.bing.com/webmaster/api.svc/json/GetQueryStats"
_DATE = re.compile(r"/Date\((-?\d+)")


def parse_bing_date(value: str) -> date:
    """`/Date(1770336000000)/` (epoch milliseconds, UTC) -> a date."""
    match = _DATE.search(value or "")
    if not match:
        raise BingError(f"Bing sent a date this tool cannot read: {value!r}")
    return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=timezone.utc).date()


def query_stats(api_key: str, site_url: str) -> list[dict]:
    """Weekly query statistics for one site, as `{week_start, query, impressions, clicks, ...}`."""
    try:
        res = httpx.get(QUERY_STATS_URL, params={"apikey": api_key, "siteUrl": site_url}, timeout=60)
    except httpx.HTTPError as exc:
        raise BingError(f"Bing Webmaster did not answer: {exc}") from exc
    if res.status_code >= 400:
        raise BingError(f"Bing Webmaster refused the request ({res.status_code}). Check the API key and site.")
    try:
        rows = res.json().get("d") or []
    except ValueError as exc:
        raise BingError("Bing Webmaster sent something that was not JSON.") from exc

    def position(value) -> float | None:
        return None if value is None or float(value) < 0 else float(value)

    out = []
    for row in rows:
        query = str(row.get("Query") or "").strip()
        if not query:
            continue
        out.append(
            {
                "week_start": parse_bing_date(row.get("Date", "")),
                "query": query,
                "impressions": int(row.get("Impressions") or 0),
                "clicks": int(row.get("Clicks") or 0),
                "avg_impression_position": position(row.get("AvgImpressionPosition")),
                "avg_click_position": position(row.get("AvgClickPosition")),
            }
        )
    return out
