from unittest.mock import MagicMock, patch

from app.ingestion.google_auth import ensure_access_token


def test_ensure_access_token_always_refreshes() -> None:
    creds = MagicMock()
    creds.expiry = object()
    creds.valid = True
    creds.token = "fresh-token"

    with patch("app.ingestion.google_auth.Request"), patch.object(creds, "refresh") as refresh:
        token = ensure_access_token(creds)

    refresh.assert_called_once()
    assert token == "fresh-token"
