"""The Google Ads API over REST, on the workspace's Google sign-in (OAuth).

The access token is minted from the same refresh token Analytics and Search Console use, asking for the Google Ads scope alone, so it works only once an
admin has reconnected Google and approved Google Ads. Calls go through the manager (MCC) account named in `GOOGLE_ADS_LOGIN_CUSTOMER_ID`. Google no
longer requires a developer token; one is sent only when `GOOGLE_ADS_DEVELOPER_TOKEN` is set.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json
from app.core.settings import get_settings
from app.ingestion.google_auth import ADS_SCOPE, credentials_from_tokens, ensure_access_token
from app.ingestion.google_credentials import _GOOGLE_PROVIDERS, workspace_google_refresh_token
from app.models.integration import Integration

BASE = "https://googleads.googleapis.com"
TIMEOUT_SECONDS = 120.0

_TOKEN_TTL = timedelta(minutes=45)
_tokens: dict[str, tuple[str, datetime]] = {}
_lock = threading.Lock()


class GoogleAdsError(RuntimeError):
    """A reason a person can act on: the permission is missing, the account is not reachable, or Google refused the query."""


def digits(value: str | None) -> str:
    """A customer ID as Google wants it: digits only (183-526-2013 is 1835262013)."""
    return "".join(ch for ch in (value or "") if ch.isdigit())


def permission_granted(db: Session) -> bool:
    """Whether the workspace's Google sign-in includes the Google Ads permission."""
    rows = db.query(Integration).filter(Integration.provider.in_(_GOOGLE_PROVIDERS), Integration.credentials.isnot(None)).yield_per(20)
    for row in rows:
        try:
            scope = str(decrypt_json(row.credentials).get("scope") or "")
        except Exception:  # noqa: BLE001
            continue
        if ADS_SCOPE in scope.split():
            return True
    return False


def reset_token_cache() -> None:
    with _lock:
        _tokens.clear()


def access_token(db: Session) -> str:
    settings = get_settings()
    if not settings.google_data_oauth_client_id or not settings.google_data_oauth_client_secret:
        raise GoogleAdsError("Google sign-in is not set up on the server (GOOGLE_DATA_OAUTH_CLIENT_ID and SECRET).")
    refresh_token = workspace_google_refresh_token(db)
    if not refresh_token:
        raise GoogleAdsError("Google is not connected. Connect Google on the Connections page first.")
    now = datetime.now(timezone.utc)
    with _lock:
        cached = _tokens.get(refresh_token)
        if cached is not None and cached[1] > now:
            return cached[0]
    creds = credentials_from_tokens(
        refresh_token=refresh_token, client_id=settings.google_data_oauth_client_id, client_secret=settings.google_data_oauth_client_secret, scopes=[ADS_SCOPE],
    )
    try:
        token = ensure_access_token(creds)
    except Exception as exc:  # noqa: BLE001
        text = str(exc).lower()
        if "invalid_scope" in text or "invalid_grant" in text:
            raise GoogleAdsError("Google Ads has not been approved on the Google connection. An admin needs to reconnect Google and approve Google Ads.") from exc
        raise GoogleAdsError("Google would not give an access token for Google Ads.") from exc
    with _lock:
        _tokens[refresh_token] = (token, now + _TOKEN_TTL)
    return token


def _headers(token: str) -> dict[str, str]:
    settings = get_settings()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if digits(settings.google_ads_login_customer_id):
        headers["login-customer-id"] = digits(settings.google_ads_login_customer_id)
    if settings.google_ads_developer_token:
        headers["developer-token"] = settings.google_ads_developer_token
    return headers


def _reason(response: httpx.Response) -> str:
    """Google's own words for what went wrong, short enough to show."""
    try:
        body = response.json()
        body = body[0] if isinstance(body, list) and body else body
        error = body.get("error", {}) if isinstance(body, dict) else {}
        detail = ""
        for d in error.get("details") or []:
            for e in d.get("errors") or []:
                detail = str(e.get("message") or "")
                if detail:
                    break
            if detail:
                break
        text = detail or str(error.get("message") or "")
        status = str(error.get("status") or response.status_code)
        return f"{status}: {text}"[:300] if text else f"Google Ads answered {response.status_code}."
    except ValueError:
        return f"Google Ads answered {response.status_code}."


def search(token: str, customer_id: str, query: str) -> list[dict[str, Any]]:
    """Every row of one query. Values keep Google's JSON shape: camelCase names, and 64-bit integers as strings."""
    settings = get_settings()
    url = f"{BASE}/{settings.google_ads_api_version}/customers/{digits(customer_id)}/googleAds:searchStream"
    try:
        response = httpx.post(url, json={"query": query}, headers=_headers(token), timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise GoogleAdsError("Google Ads could not be reached.") from exc
    if response.status_code >= 400:
        raise GoogleAdsError(_reason(response))
    body = response.json()
    batches = body if isinstance(body, list) else [body]
    return [row for batch in batches for row in batch.get("results", [])]


ACCOUNTS_QUERY = (
    "SELECT customer_client.id, customer_client.descriptive_name, customer_client.manager, customer_client.status "
    "FROM customer_client WHERE customer_client.level <= 1 AND customer_client.status = 'ENABLED'"
)


def list_accounts(token: str) -> list[dict[str, Any]]:
    """The client accounts under the manager account, for choosing which one a client is."""
    manager = digits(get_settings().google_ads_login_customer_id)
    if not manager:
        raise GoogleAdsError("The manager account is not set. Set GOOGLE_ADS_LOGIN_CUSTOMER_ID to its ID (digits only).")
    out = []
    for row in search(token, manager, ACCOUNTS_QUERY):
        c = row.get("customerClient") or {}
        if c.get("manager") or not c.get("id"):
            continue
        out.append({"id": str(c["id"]), "name": str(c.get("descriptiveName") or c["id"])})
    out.sort(key=lambda a: a["name"].lower())
    return out
