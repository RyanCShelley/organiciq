from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
ADS_SCOPE = "https://www.googleapis.com/auth/adwords"
#: What the sync's credentials are built with. Google Ads is left out on purpose: a refresh that asks for a scope the grant lacks fails, and
#: Analytics and Search Console must keep working for a grant made before Google Ads was added.
DATA_OAUTH_SCOPES = [GSC_SCOPE, GA4_SCOPE]
#: What the connect screen asks for.
CONNECT_SCOPES = [*DATA_OAUTH_SCOPES, ADS_SCOPE]


def credentials_from_tokens(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    token: str | None = None,
    scopes: list[str] | None = None,
) -> Credentials:
    return Credentials(
        token=token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes or DATA_OAUTH_SCOPES,
    )


def ensure_access_token(creds: Credentials) -> str:
    # Always refresh for server-side jobs and UI calls — stored access tokens have no expiry.
    creds.refresh(Request())
    if not creds.token:
        raise RuntimeError("Failed to obtain Google access token")
    return creds.token
