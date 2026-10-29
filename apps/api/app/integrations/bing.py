"""Bing Webmaster Tools: which sites the workspace's API key can see."""

from __future__ import annotations

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
