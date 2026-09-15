import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.settings import get_settings


def _fernet_for(secret: str) -> Fernet:
    # Derive a stable 32-byte Fernet key from the configured secret.
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _fernet() -> Fernet:
    return _fernet_for(get_settings().integration_token_key)


def _previous_fernet() -> Fernet | None:
    """
    Key being rotated away from, if any.

    INTEGRATION_TOKEN_KEY cannot simply be changed: it derives the Fernet key
    for every stored Google refresh token, so a bare swap makes all of them
    undecryptable and forces every client to reconnect. Setting
    INTEGRATION_TOKEN_KEY_PREVIOUS lets reads fall back while
    `python -m app.rotate_integration_key` re-encrypts in place.
    """
    previous = get_settings().integration_token_key_previous
    return _fernet_for(previous) if previous else None


def encrypt_json(payload: dict[str, Any]) -> str:
    token = _fernet().encrypt(json.dumps(payload).encode("utf-8"))
    return token.decode("utf-8")


def decrypt_json(token: str) -> dict[str, Any]:
    raw_token = token.encode("utf-8")
    try:
        raw = _fernet().decrypt(raw_token)
    except InvalidToken:
        previous = _previous_fernet()
        if previous is None:
            raise
        # Written under the old key and not yet rotated.
        raw = previous.decrypt(raw_token)
    return json.loads(raw.decode("utf-8"))
