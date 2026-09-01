import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet

from app.core.settings import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    raw = settings.integration_token_key.encode("utf-8")
    # Derive a stable 32-byte Fernet key from the configured secret.
    digest = hashlib.sha256(raw).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_json(payload: dict[str, Any]) -> str:
    token = _fernet().encrypt(json.dumps(payload).encode("utf-8"))
    return token.decode("utf-8")


def decrypt_json(token: str) -> dict[str, Any]:
    raw = _fernet().decrypt(token.encode("utf-8"))
    return json.loads(raw.decode("utf-8"))
