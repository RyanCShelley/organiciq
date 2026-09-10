from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json, encrypt_json
from app.core.settings import get_settings
from app.ingestion.google_auth import DATA_OAUTH_SCOPES, credentials_from_tokens, ensure_access_token
from app.models.client import Client
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider

_GOOGLE_PROVIDERS = (IntegrationProvider.GSC, IntegrationProvider.GA4)

# Google access tokens live ~1h. Cache per refresh token (the grant is shared
# workspace-wide) so a daily cycle spends one token request instead of one per
# fetch call, and refresh a little early to avoid mid-job expiry.
_TOKEN_EXPIRY_SKEW = timedelta(minutes=5)
_FALLBACK_TOKEN_TTL = timedelta(minutes=45)
_token_cache: dict[str, tuple[str, datetime]] = {}
_token_lock = threading.Lock()


def reset_access_token_cache() -> None:
    """Drop cached access tokens (tests, and after a reconnect)."""
    with _token_lock:
        _token_cache.clear()


def _integration_row(db: Session, client_id: UUID, provider: IntegrationProvider) -> Integration | None:
    return (
        db.query(Integration)
        .filter(Integration.client_id == client_id, Integration.provider == provider)
        .one_or_none()
    )


def _refresh_token_from_row(integration: Integration | None) -> str | None:
    if integration is None or not integration.credentials:
        return None
    try:
        refresh_token = decrypt_json(integration.credentials).get("refresh_token")
    except Exception:  # noqa: BLE001
        return None
    return str(refresh_token) if refresh_token else None


def workspace_google_refresh_token(db: Session) -> str | None:
    """Any client's Google Data OAuth grant — shared across the workspace."""
    # Streamed, not .all(): every row holds the same grant, so the first hit
    # wins and we avoid decrypting ~70 blobs to answer one question.
    rows = (
        db.query(Integration)
        .filter(
            Integration.provider.in_(_GOOGLE_PROVIDERS),
            Integration.credentials.isnot(None),
        )
        .yield_per(20)
    )
    for row in rows:
        refresh_token = _refresh_token_from_row(row)
        if refresh_token:
            return refresh_token
    return None


def load_google_refresh_token(db: Session, client_id: UUID) -> str:
    """Prefer this client's grant, then fall back to any workspace Google connection."""
    for provider in _GOOGLE_PROVIDERS:
        refresh_token = _refresh_token_from_row(_integration_row(db, client_id, provider))
        if refresh_token:
            return refresh_token

    shared = workspace_google_refresh_token(db)
    if shared:
        return shared
    raise RuntimeError("Google is not connected (missing refresh_token on GSC/GA4 integrations)")


def client_has_google_credentials(db: Session, client_id: UUID) -> bool:
    try:
        load_google_refresh_token(db, client_id)
        return True
    except RuntimeError:
        return False


def upsert_google_credentials_for_client(
    db: Session, client_id: UUID, cred_payload: dict, *, commit: bool = False
) -> None:
    """Write Google tokens onto this client's GSC + GA4 rows (property mapping unchanged)."""
    for provider in _GOOGLE_PROVIDERS:
        integration = _integration_row(db, client_id, provider)
        if integration is None:
            integration = Integration(client_id=client_id, provider=provider)
            db.add(integration)

        existing: dict = {}
        if integration.credentials:
            try:
                existing = decrypt_json(integration.credentials)
            except Exception:  # noqa: BLE001
                existing = {}

        merged = {
            "refresh_token": cred_payload.get("refresh_token") or existing.get("refresh_token"),
            "token": cred_payload.get("token") or existing.get("token"),
            "token_type": cred_payload.get("token_type", existing.get("token_type", "Bearer")),
            "scope": cred_payload.get("scope") or existing.get("scope") or " ".join(DATA_OAUTH_SCOPES),
        }
        integration.credentials = encrypt_json(merged)
        integration.connection_status = ConnectionStatus.CONNECTED
        integration.error_message = None

    if commit:
        db.commit()


def propagate_google_credentials(db: Session, cred_payload: dict) -> None:
    """Apply one Google Data OAuth grant to every client (internal workspace sharing)."""
    client_ids = [row.id for row in db.query(Client.id).all()]
    for client_id in client_ids:
        upsert_google_credentials_for_client(db, client_id, cred_payload, commit=False)
    db.commit()
    # A reconnect may replace the grant; never serve a token from the old one.
    reset_access_token_cache()


def _mint_access_token(refresh_token: str) -> tuple[str, datetime]:
    settings = get_settings()
    creds = credentials_from_tokens(
        refresh_token=refresh_token,
        client_id=settings.google_data_oauth_client_id,
        client_secret=settings.google_data_oauth_client_secret,
        token=None,
    )
    try:
        token = ensure_access_token(creds)
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "invalid_grant" in message.lower():
            raise RuntimeError(
                "Google OAuth refresh failed — reconnect Google in Clients → Integrations"
            ) from exc
        raise

    expiry = getattr(creds, "expiry", None)
    if expiry is None:
        expiry = datetime.now(timezone.utc) + _FALLBACK_TOKEN_TTL
    elif expiry.tzinfo is None:
        # google-auth returns a naive UTC datetime.
        expiry = expiry.replace(tzinfo=timezone.utc)
    return token, expiry


def access_token_for_client(db: Session, client_id: UUID) -> str:
    """
    Return a Google access token for ingestion, reusing a cached one when valid.

    Previously this refreshed on every call and then rewrote the encrypted
    credential blob for *every* client (2 rows each). At 35 clients that was
    ~140 token requests and ~9,800 encrypted writes per daily cycle, growing
    with the square of the client count. The stored access token is never read
    back — only `refresh_token` is — so persisting it here bought nothing.
    """
    settings = get_settings()
    if not settings.google_data_oauth_client_id or not settings.google_data_oauth_client_secret:
        raise RuntimeError("GOOGLE_DATA_OAUTH_CLIENT_ID/SECRET not configured")

    refresh_token = load_google_refresh_token(db, client_id)
    now = datetime.now(timezone.utc)

    with _token_lock:
        cached = _token_cache.get(refresh_token)
        if cached is not None and cached[1] - _TOKEN_EXPIRY_SKEW > now:
            return cached[0]

    token, expiry = _mint_access_token(refresh_token)

    with _token_lock:
        _token_cache[refresh_token] = (token, expiry)
    return token
