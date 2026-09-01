from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json, encrypt_json
from app.core.settings import get_settings
from app.ingestion.google_auth import DATA_OAUTH_SCOPES, credentials_from_tokens, ensure_access_token
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider

_GOOGLE_PROVIDERS = (IntegrationProvider.GSC, IntegrationProvider.GA4)


def _integration_row(db: Session, client_id: UUID, provider: IntegrationProvider) -> Integration | None:
    return (
        db.query(Integration)
        .filter(Integration.client_id == client_id, Integration.provider == provider)
        .one_or_none()
    )


def load_google_refresh_token(db: Session, client_id: UUID) -> str:
    """Return refresh token from GSC or GA4 integration (same Google Data OAuth grant)."""
    for provider in _GOOGLE_PROVIDERS:
        integration = _integration_row(db, client_id, provider)
        if integration is None or not integration.credentials:
            continue
        refresh_token = decrypt_json(integration.credentials).get("refresh_token")
        if refresh_token:
            return str(refresh_token)
    raise RuntimeError("Google is not connected (missing refresh_token on GSC/GA4 integrations)")


def persist_google_tokens(db: Session, client_id: UUID, *, refresh_token: str, access_token: str) -> None:
    """Keep GSC + GA4 integration rows on the same refreshed credential payload."""
    payload = encrypt_json(
        {
            "refresh_token": refresh_token,
            "token": access_token,
            "token_type": "Bearer",
            "scope": " ".join(DATA_OAUTH_SCOPES),
        }
    )
    for provider in _GOOGLE_PROVIDERS:
        integration = _integration_row(db, client_id, provider)
        if integration is None:
            integration = Integration(client_id=client_id, provider=provider)
            db.add(integration)
        integration.credentials = payload
        integration.connection_status = ConnectionStatus.CONNECTED
        integration.error_message = None
    db.commit()


def access_token_for_client(db: Session, client_id: UUID) -> str:
    """Always mint a fresh Google access token for ingestion jobs."""
    settings = get_settings()
    if not settings.google_data_oauth_client_id or not settings.google_data_oauth_client_secret:
        raise RuntimeError("GOOGLE_DATA_OAUTH_CLIENT_ID/SECRET not configured")

    refresh_token = load_google_refresh_token(db, client_id)
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
    persist_google_tokens(db, client_id, refresh_token=refresh_token, access_token=token)
    return token
