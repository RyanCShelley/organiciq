from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.integrations import google_ads
from app.models.ads import AdsDaily, AdsMarketDaily, AdsSearchTerm
from app.services import ads_pull
from tests.conftest import client_header

TODAY = date(2026, 11, 5)


def fake_search(calls):
    """Google's answers in the shape the REST API sends them: camelCase, and 64-bit integers as strings."""

    def search(token, customer, query):
        calls.append((customer, query))
        if "FROM ad_group" in query:
            return [
                {"segments": {"date": "2026-11-03", "device": "MOBILE"}, "campaign": {"name": "Pool"}, "adGroup": {"name": "pool leak"}, "metrics": {"impressions": "100", "clicks": "5", "costMicros": "62500000", "conversions": 1.5, "searchImpressionShare": 0.25}},
                {"segments": {"date": "2026-11-03", "device": "MOBILE"}, "campaign": {"name": "Pool"}, "adGroup": {"name": "pool leak"}, "metrics": {"impressions": "20", "clicks": "1", "costMicros": "10000000"}},
                {"segments": {"date": "2026-11-04", "device": "DESKTOP"}, "campaign": {"name": "Pool"}, "adGroup": {"name": "pool leak"}, "metrics": {"impressions": "50", "clicks": "2", "costMicros": "24000000", "searchImpressionShare": 0.5}},
            ]
        if "search_term_view" in query:
            return [{"segments": {"date": "2026-11-03"}, "searchTermView": {"searchTerm": "pool leak detection near me"}, "adGroup": {"name": "pool leak"}, "metrics": {"impressions": "9", "clicks": "3", "costMicros": "30000000"}}]
        if "geographic_view" in query:
            return [
                {"segments": {"date": "2026-11-03"}, "campaign": {"name": "Pool"}, "geographicView": {"countryCriterionId": "2840"}, "metrics": {"impressions": "100", "clicks": "5", "costMicros": "62500000"}},
                {"segments": {"date": "2026-11-03"}, "campaign": {"name": "Pool"}, "geographicView": {"countryCriterionId": "2392"}, "metrics": {"impressions": "20", "clicks": "1", "costMicros": "10000000"}},
            ]
        if "geo_target_constant" in query:
            return [{"geoTargetConstant": {"id": "2392", "name": "Japan"}}]
        raise AssertionError(query)

    return search


@pytest.fixture
def ads_client(db, client_a, monkeypatch):
    client_a.service_reporting = {"organiciq": True, "ad_accelerator": True}
    client_a.google_ads_customer_id = "1835262013"
    db.commit()
    calls: list = []
    monkeypatch.setattr(google_ads, "access_token", lambda db: "token")
    monkeypatch.setattr(google_ads, "search", fake_search(calls))
    return client_a, calls


def test_a_pull_turns_googles_rows_into_days_terms_and_markets_and_clears_the_demo(db, ads_client):
    client, calls = ads_client
    db.add(AdsDaily(client_id=client.id, date=date(2026, 8, 1), campaign="Demo", ad_group="demo", device="Desktop", impressions=1, clicks=1, cost=Decimal("1"), source="demo"))
    db.add(AdsSearchTerm(client_id=client.id, date=date(2026, 8, 1), term="demo term", ad_group="demo", clicks=1, source="demo"))
    db.add(AdsMarketDaily(client_id=client.id, date=date(2026, 8, 1), campaign="Demo", market="Nowhere", clicks=1, source="demo"))
    db.commit()
    stats = ads_pull.pull(db, client, today=TODAY)
    assert stats["from"] == (TODAY - timedelta(days=90)).isoformat() and stats["days"] == 2 and stats["rows"] == 2 and stats["terms"] == 1 and stats["markets"] == 2
    days = {(r.date, r.device): r for r in db.query(AdsDaily).filter(AdsDaily.client_id == client.id)}
    assert set(days) == {(date(2026, 11, 3), "Mobile"), (date(2026, 11, 4), "Desktop")}, "the demo row is gone; devices read as words"
    mobile = days[(date(2026, 11, 3), "Mobile")]
    assert (mobile.impressions, mobile.clicks, mobile.cost, mobile.conversions) == (120, 6, Decimal("72.50"), Decimal("1.5")) and mobile.eligible_impressions == 400 and mobile.source == "google_ads"
    assert days[(date(2026, 11, 4), "Desktop")].eligible_impressions == 100
    assert {m.market: m.clicks for m in db.query(AdsMarketDaily).filter(AdsMarketDaily.client_id == client.id)} == {"United States": 5, "Japan": 1}
    assert [(t.term, t.clicks) for t in db.query(AdsSearchTerm).filter(AdsSearchTerm.client_id == client.id)] == [("pool leak detection near me", 3)]
    assert client.google_ads_last_pull_at is not None and client.google_ads_last_error is None
    assert all(c[0] == "1835262013" for c in calls) and len(calls) == 4, "the account is used as digits; Japan is looked up, the United States is known"


def test_a_later_pull_reaches_back_two_weeks_and_replaces_the_window(db, ads_client):
    client, _ = ads_client
    ads_pull.pull(db, client, today=TODAY)
    again = ads_pull.pull(db, client, today=TODAY)
    assert again["from"] == (TODAY - timedelta(days=14)).isoformat()
    assert db.query(AdsDaily).filter(AdsDaily.client_id == client.id).count() == 2, "the same days are not added twice"


def test_a_pull_needs_an_account_and_says_so(db, client_a):
    with pytest.raises(google_ads.GoogleAdsError, match="No Google Ads account"):
        ads_pull.pull(db, client_a, today=TODAY)


def test_the_daily_run_pulls_each_client_on_ads_accelerator_and_records_a_failure_without_stopping(db, ads_client, monkeypatch):
    client, _ = ads_client
    monkeypatch.setattr(ads_pull.get_settings(), "ads_pull_hour_utc", 0)

    def refuse(token, customer, query):
        raise google_ads.GoogleAdsError("PERMISSION_DENIED: the account is not linked to the manager account")

    monkeypatch.setattr(google_ads, "search", refuse)
    assert ads_pull.maybe_pull_ads(db) is True
    db.refresh(client)
    assert "not linked" in client.google_ads_last_error and client.google_ads_last_pull_at is None
    assert ads_pull.maybe_pull_ads(db) is False, "once a day"


def test_googles_rest_rows_are_read_and_its_errors_are_put_in_plain_words(monkeypatch):
    seen = {}

    def post(url, json, headers, timeout):
        seen.update(url=url, headers=headers, body=json)
        return httpx.Response(200, json=[{"results": [{"a": 1}]}, {"results": [{"a": 2}]}], request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(google_ads.get_settings(), "google_ads_login_customer_id", "183-526-2013")
    assert google_ads.search("tok", "393-169-919", "SELECT 1") == [{"a": 1}, {"a": 2}]
    assert seen["url"].endswith("/customers/393169919/googleAds:searchStream") and seen["headers"]["login-customer-id"] == "1835262013" and "developer-token" not in seen["headers"]
    bad = httpx.Response(403, json=[{"error": {"status": "PERMISSION_DENIED", "message": "x", "details": [{"errors": [{"message": "User doesn't have permission to access customer."}]}]}}], request=httpx.Request("POST", "http://x"))
    assert google_ads._reason(bad) == "PERMISSION_DENIED: User doesn't have permission to access customer."
    assert google_ads.digits("183-526-2013") == "1835262013"


def test_the_connection_can_be_read_chosen_and_pulled_by_an_admin(client, db, client_a, admin_user, team_user, monkeypatch):
    client_a.service_reporting = {"organiciq": True, "ad_accelerator": True}
    db.commit()
    hd, ht = client_header(client_a.id, admin_user.email), client_header(client_a.id, team_user.email)
    state = client.get("/v2/ads/connection", headers=hd).json()
    assert state["customer_id"] is None and state["permission"] is False and state["enabled"] is True
    assert client.put("/v2/ads/connection", json={"customer_id": "12345"}, headers=hd).status_code == 400
    assert client.put("/v2/ads/connection", json={"customer_id": "183-526-2013"}, headers=ht).status_code == 403, "choosing the account is for admins"
    assert client.put("/v2/ads/connection", json={"customer_id": "183-526-2013"}, headers=hd).json() == {"customer_id": "1835262013"}
    monkeypatch.setattr(google_ads, "access_token", lambda db: "token")
    monkeypatch.setattr(google_ads, "list_accounts", lambda token: [{"id": "1835262013", "name": "Demo"}])
    assert client.get("/v2/ads/accounts", headers=hd).json() == {"accounts": [{"id": "1835262013", "name": "Demo"}]}
    monkeypatch.setattr(google_ads, "search", fake_search([]))
    pulled = client.post("/v2/ads/pull", headers=hd)
    assert pulled.status_code == 200 and pulled.json()["rows"] == 2

    def refuse(token, customer, query):
        raise google_ads.GoogleAdsError("Google Ads has not been approved on the Google connection.")

    monkeypatch.setattr(google_ads, "search", refuse)
    failed = client.post("/v2/ads/pull", headers=hd)
    assert failed.status_code == 502 and "not been approved" in failed.json()["detail"]
    assert "not been approved" in client.get("/v2/ads/connection", headers=hd).json()["last_error"]
