"""Bing and Teamwork on v2's Connections screen, and where Google connect returns to."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.api.routers import oauth_google as oauth
from app.core.settings import get_settings
from app.integrations import bing
from app.models.client_bing_site import ClientBingSite
from tests.conftest import client_header

SITES = [
    {"url": "https://zz.example/", "verified": True},
    {"url": "https://other.example/", "verified": False},
]


@pytest.fixture()
def bing_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "bing_webmaster_api_key", "test-key")
    monkeypatch.setattr(bing, "list_sites", lambda key: SITES)


def test_with_no_bing_key_a_site_is_saved_unchecked(client, db, client_a, admin_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "bing_webmaster_api_key", "")
    headers = client_header(client_a.id, admin_user.email)

    saved = client.put("/v2/connections/bing", json={"site_url": "https://zz.example/"}, headers=headers)
    assert saved.status_code == 200 and saved.json()["status"] == "unchecked"

    state = client.get("/v2/connections", headers=headers).json()
    assert state["bing_key_configured"] is False
    assert state["bing"]["site_url"] == "https://zz.example/"


def test_a_verified_site_on_the_account_is_connected(client, db, client_a, admin_user, bing_key):
    headers = client_header(client_a.id, admin_user.email)
    saved = client.put("/v2/connections/bing", json={"site_url": "https://ZZ.example"}, headers=headers)
    assert saved.json()["status"] == "connected" and saved.json()["checked_at"] is not None


def test_a_site_bing_does_not_know_is_an_error_with_a_reason(client, db, client_a, admin_user, bing_key):
    headers = client_header(client_a.id, admin_user.email)
    saved = client.put("/v2/connections/bing", json={"site_url": "https://nope.example/"}, headers=headers)
    assert saved.json()["status"] == "error"
    assert "not on the Bing Webmaster account" in saved.json()["error"]


def test_a_listed_but_unverified_site_is_an_error(client, db, client_a, admin_user, bing_key):
    headers = client_header(client_a.id, admin_user.email)
    saved = client.put("/v2/connections/bing", json={"site_url": "https://other.example/"}, headers=headers)
    assert saved.json()["status"] == "error" and "not verified" in saved.json()["error"]


def test_a_bing_failure_is_reported_not_swallowed(client, db, client_a, admin_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "bing_webmaster_api_key", "bad")

    def boom(key):
        raise bing.BingError("Bing Webmaster refused the request (401). Check the API key.")

    monkeypatch.setattr(bing, "list_sites", boom)
    response = client.put(
        "/v2/connections/bing",
        json={"site_url": "https://zz.example/"},
        headers=client_header(client_a.id, admin_user.email),
    )
    assert response.status_code == 502 and "API key" in response.json()["detail"]
    assert db.query(ClientBingSite).count() == 0


def test_a_site_that_is_not_a_web_address_is_refused(client, db, client_a, admin_user, bing_key):
    response = client.put(
        "/v2/connections/bing",
        json={"site_url": "zz.example"},
        headers=client_header(client_a.id, admin_user.email),
    )
    assert response.status_code == 400


def test_the_choices_come_from_bing(client, db, client_a, admin_user, bing_key):
    sites = client.get("/v2/connections/bing/sites", headers=client_header(client_a.id, admin_user.email))
    assert [s["url"] for s in sites.json()] == ["https://zz.example/", "https://other.example/"]


def test_bing_sites_are_kept_apart_per_client_and_can_be_cleared(
    client, db, client_a, client_b, admin_user, bing_key
):
    a = client_header(client_a.id, admin_user.email)
    b = client_header(client_b.id, admin_user.email)
    client.put("/v2/connections/bing", json={"site_url": "https://zz.example/"}, headers=a)

    assert client.get("/v2/connections", headers=b).json()["bing"] is None
    assert client.delete("/v2/connections/bing", headers=a).status_code == 204
    assert client.get("/v2/connections", headers=a).json()["bing"] is None


def test_teamwork_reports_whether_the_install_is_configured(client, db, client_a, admin_user, monkeypatch):
    headers = client_header(client_a.id, admin_user.email)
    monkeypatch.delenv("TEAMWORK_SITE", raising=False)
    monkeypatch.delenv("TEAMWORK_API_TOKEN", raising=False)
    assert client.get("/v2/connections", headers=headers).json()["teamwork_configured"] is False

    monkeypatch.setenv("TEAMWORK_SITE", "sma")
    monkeypatch.setenv("TEAMWORK_API_TOKEN", "t")
    assert client.get("/v2/connections", headers=headers).json()["teamwork_configured"] is True


def _start(client, client_a, admin_user, **params):
    return client.get(
        "/oauth/google/start",
        params={"client_id": str(client_a.id), **params},
        headers=client_header(client_a.id, admin_user.email),
    )


def _callback_location(client, **params):
    return client.get("/oauth/google/callback", params=params, follow_redirects=False).headers["location"]


def test_connect_started_by_v2_returns_to_v2(client, db, client_a, admin_user, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "google_data_oauth_client_id", "id")
    monkeypatch.setattr(s, "google_data_oauth_client_secret", "secret")
    oauth._oauth_states.clear()
    assert _start(client, client_a, admin_user, return_to="v2").status_code == 200
    state = next(iter(oauth._oauth_states))

    location = _callback_location(client, error="access_denied", state=state)
    assert location.startswith(f"{s.web_v2_app_url.rstrip('/')}/{client_a.slug}/settings/connections?")
    assert "oauth=error" in location and "access_denied" in location


def test_connect_started_the_old_way_still_returns_to_the_old_tool(client, db, client_a, admin_user, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "google_data_oauth_client_id", "id")
    monkeypatch.setattr(s, "google_data_oauth_client_secret", "secret")
    oauth._oauth_states.clear()
    assert _start(client, client_a, admin_user).status_code == 200
    state = next(iter(oauth._oauth_states))

    location = _callback_location(client, error="access_denied", state=state)
    assert location.startswith(f"{s.web_app_url.rstrip('/')}/clients?")


def test_an_unknown_state_cannot_steer_the_redirect_to_v2(client, db, client_a, admin_user):
    oauth._oauth_states.clear()
    location = _callback_location(client, code="x", state="made-up")
    assert location.startswith(get_settings().web_app_url.rstrip("/"))
    assert "invalid_state" in location


def test_return_to_only_accepts_the_two_known_values(client, db, client_a, admin_user, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "google_data_oauth_client_id", "id")
    monkeypatch.setattr(s, "google_data_oauth_client_secret", "secret")
    assert _start(client, client_a, admin_user, return_to="https://evil.example").status_code == 422
