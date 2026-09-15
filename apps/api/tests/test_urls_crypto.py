import pytest

from app.core.crypto import decrypt_json, encrypt_json
from app.core.urls import normalize_landing_page, normalize_url, rewrite_url_host


def test_normalize_url_strips_www_query_fragment_and_slash():
    assert (
        normalize_url("HTTPS://WWW.Example.com/Path/?utm=1#frag")
        == "https://example.com/path"
    )


def test_normalize_url_adds_https_when_missing():
    assert normalize_url("example.com/a") == "https://example.com/a"


def test_normalize_landing_page_prefixes_path_with_domain():
    assert normalize_landing_page("/Home/", "WWW.smamarketing.net") == "https://smamarketing.net/home"


def test_normalize_landing_page_keeps_ga4_sentinels():
    assert normalize_landing_page("(not set)") == "(not set)"
    assert normalize_landing_page("") == ""


def test_rewrite_url_host_replaces_host_keeps_path():
    assert (
        rewrite_url_host("https://old.example/Path/Page?x=1", "WWW.new.example")
        == "https://new.example/Path/Page?x=1"
    )


def test_rewrite_url_host_accepts_domain_with_scheme():
    assert (
        rewrite_url_host("http://legacy.com/a", "https://smamarketing.net")
        == "http://smamarketing.net/a"
    )


def test_encrypt_decrypt_roundtrip():
    payload = {"refresh_token": "rt-123", "token": "at-456"}
    token = encrypt_json(payload)
    assert token != "rt-123"
    assert decrypt_json(token) == payload


# --- Key rotation -----------------------------------------------------------
#
# INTEGRATION_TOKEN_KEY derives the Fernet key for stored Google refresh
# tokens, so a bare swap makes every grant undecryptable and forces all
# clients to reconnect. Rotation has to read old and write new.


def test_decrypt_falls_back_to_the_previous_key(monkeypatch):
    from app.core import crypto
    from app.core.settings import Settings

    old_key = "old-" + "o" * 44
    new_key = "new-" + "n" * 44

    monkeypatch.setattr(
        crypto, "get_settings", lambda: Settings(integration_token_key=old_key)
    )
    blob = crypto.encrypt_json({"refresh_token": "rt-123"})

    # Key swapped, old one still declared.
    monkeypatch.setattr(
        crypto,
        "get_settings",
        lambda: Settings(
            integration_token_key=new_key, integration_token_key_previous=old_key
        ),
    )

    assert crypto.decrypt_json(blob) == {"refresh_token": "rt-123"}


def test_decrypt_fails_without_the_previous_key(monkeypatch):
    """A bare swap must fail loudly, not silently return nothing."""
    from cryptography.fernet import InvalidToken

    from app.core import crypto
    from app.core.settings import Settings

    old_key = "old-" + "o" * 44
    new_key = "new-" + "n" * 44

    monkeypatch.setattr(
        crypto, "get_settings", lambda: Settings(integration_token_key=old_key)
    )
    blob = crypto.encrypt_json({"refresh_token": "rt-123"})

    monkeypatch.setattr(
        crypto, "get_settings", lambda: Settings(integration_token_key=new_key)
    )

    with pytest.raises(InvalidToken):
        crypto.decrypt_json(blob)


def test_rewriting_under_the_new_key_removes_the_dependency(monkeypatch):
    """After rotation the blob reads with the new key alone."""
    from app.core import crypto
    from app.core.settings import Settings

    old_key = "old-" + "o" * 44
    new_key = "new-" + "n" * 44

    monkeypatch.setattr(
        crypto, "get_settings", lambda: Settings(integration_token_key=old_key)
    )
    blob = crypto.encrypt_json({"refresh_token": "rt-123"})

    monkeypatch.setattr(
        crypto,
        "get_settings",
        lambda: Settings(
            integration_token_key=new_key, integration_token_key_previous=old_key
        ),
    )
    rotated = crypto.encrypt_json(crypto.decrypt_json(blob))

    monkeypatch.setattr(
        crypto, "get_settings", lambda: Settings(integration_token_key=new_key)
    )
    assert crypto.decrypt_json(rotated) == {"refresh_token": "rt-123"}
