from app.core.crypto import decrypt_json, encrypt_json
from app.core.urls import normalize_landing_page, normalize_url


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


def test_encrypt_decrypt_roundtrip():
    payload = {"refresh_token": "rt-123", "token": "at-456"}
    token = encrypt_json(payload)
    assert token != "rt-123"
    assert decrypt_json(token) == payload
