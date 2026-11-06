from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.integrations import google_ads
from app.models.ads import AdsDaily, AdsMarketDaily, AdsSearchTerm, ClientAdsAccount
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
    db.add(ClientAdsAccount(client_id=client_a.id, customer_id="1835262013", name="Aquaman", kind="ads"))
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
    account = db.query(ClientAdsAccount).filter(ClientAdsAccount.client_id == client.id).one()
    assert account.last_pull_at is not None and account.last_error is None
    assert all(c[0] == "1835262013" for c in calls) and len(calls) == 4, "the account is used as digits; Japan is looked up, the United States is known"


def test_a_later_pull_reaches_back_two_weeks_and_replaces_the_window(db, ads_client):
    client, _ = ads_client
    ads_pull.pull(db, client, today=TODAY)
    again = ads_pull.pull(db, client, today=TODAY)
    assert again["from"] == (TODAY - timedelta(days=14)).isoformat()
    assert db.query(AdsDaily).filter(AdsDaily.client_id == client.id).count() == 2, "the same days are not added twice"


def test_a_client_can_have_several_accounts_and_an_lsa_account_is_read_by_campaign(db, ads_client, monkeypatch):
    client, calls = ads_client
    db.add(ClientAdsAccount(client_id=client.id, customer_id="9876543210", name="Aquaman LSA", kind="lsa"))
    db.commit()

    def search(token, customer, query):
        calls.append((customer, query))
        if customer == "9876543210":
            assert "LOCAL_SERVICES" in query
            return [{"segments": {"date": "2026-11-03"}, "campaign": {"name": "Local Services"}, "metrics": {"impressions": "40", "clicks": "7", "costMicros": "140000000"}}]
        return fake_search([])(token, customer, query)

    monkeypatch.setattr(google_ads, "search", search)
    stats = ads_pull.pull(db, client, today=TODAY)
    assert len(stats["accounts"]) == 2 and stats["errors"] == []
    mine = {(r.account_id, r.ad_group): r for r in db.query(AdsDaily).filter(AdsDaily.client_id == client.id)}
    assert ("9876543210", "Local Services") in mine and mine[("9876543210", "Local Services")].cost == Decimal("140.00") and mine[("9876543210", "Local Services")].device == ""
    assert {r.account_id for r in db.query(AdsDaily).filter(AdsDaily.client_id == client.id)} == {"1835262013", "9876543210"}
    # one account failing is recorded on it, the other still pulls
    def half(token, customer, query):
        if customer == "9876543210":
            raise google_ads.GoogleAdsError("PERMISSION_DENIED: not linked")
        return fake_search([])(token, customer, query)

    monkeypatch.setattr(google_ads, "search", half)
    again = ads_pull.pull(db, client, today=TODAY)
    assert len(again["accounts"]) == 1 and "Aquaman LSA: PERMISSION_DENIED" in again["errors"][0]
    lsa = db.query(ClientAdsAccount).filter(ClientAdsAccount.customer_id == "9876543210").one()
    assert "not linked" in lsa.last_error
    assert db.query(AdsDaily).filter(AdsDaily.client_id == client.id, AdsDaily.account_id == "9876543210").count() == 1, "its earlier rows stay when its refresh fails"


def test_google_ads_is_a_pull_data_source_and_runs_as_a_job(db, ads_client):
    from app.models.job import SyncJob, SyncJobStatus
    from app.schemas import SyncJobCreate
    from app.services import data_pull, jobs

    client, _ = ads_client
    plan = {p["source"]: p for p in data_pull.pull_plan(db, client, today=TODAY)}
    assert plan["google_ads"]["label"] == "Google Ads" and "90 days" in plan["google_ads"]["reach"]
    job = jobs.enqueue_sync_job(db, client.id, SyncJobCreate(source="google_ads", start_date=TODAY, end_date=TODAY))
    done = jobs.process_job(db, db.get(SyncJob, job.id))
    assert done.status == SyncJobStatus.SUCCESSFUL and done.records_written == 2 and "through" in done.error_message


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
    from app.models.job import SyncJob

    jobs = db.query(SyncJob).filter(SyncJob.client_id == client.id, SyncJob.source == "google_ads").all()
    assert len(jobs) == 1, "queued as a job, so it shows in Pull data"
    from app.services import jobs as job_runner

    done = job_runner.process_job(db, jobs[0])
    assert done.status.value == "failed" and "not linked" in done.error_message
    account = db.query(ClientAdsAccount).filter(ClientAdsAccount.client_id == client.id).one()
    assert "not linked" in account.last_error and account.last_pull_at is None
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


def test_accounts_can_be_added_removed_and_pulled_by_an_admin(client, db, client_a, admin_user, team_user, monkeypatch):
    client_a.service_reporting = {"organiciq": True, "ad_accelerator": True}
    db.commit()
    hd, ht = client_header(client_a.id, admin_user.email), client_header(client_a.id, team_user.email)
    state = client.get("/v2/ads/connection", headers=hd).json()
    assert state["accounts"] == [] and state["permission"] is False and state["enabled"] is True
    assert client.post("/v2/ads/accounts", json={"customer_id": "12345"}, headers=hd).status_code == 400
    assert client.post("/v2/ads/accounts", json={"customer_id": "183-526-2013"}, headers=ht).status_code == 403, "choosing accounts is for admins"
    one = client.post("/v2/ads/accounts", json={"customer_id": "183-526-2013", "name": "Aquaman"}, headers=hd).json()
    two = client.post("/v2/ads/accounts", json={"customer_id": "987-654-3210", "name": "Aquaman LSA", "kind": "lsa"}, headers=hd).json()
    assert one["customer_id"] == "1835262013" and one["kind"] == "ads" and two["kind"] == "lsa"
    assert [a["customer_id"] for a in client.get("/v2/ads/connection", headers=hd).json()["accounts"]] == ["1835262013", "9876543210"]
    monkeypatch.setattr(google_ads, "access_token", lambda db: "token")
    monkeypatch.setattr(google_ads, "list_accounts", lambda token: [{"id": "1835262013", "name": "Demo"}])
    assert client.get("/v2/ads/available", headers=hd).json() == {"accounts": [{"id": "1835262013", "name": "Demo"}]}
    monkeypatch.setattr(google_ads, "search", lambda token, customer, query: fake_search([])(token, customer, query) if customer == "1835262013" else [])
    pulled = client.post("/v2/ads/pull", headers=hd)
    assert pulled.status_code == 200 and pulled.json()["rows"] == 2 and len(pulled.json()["accounts"]) == 2
    assert client.delete("/v2/ads/accounts/987-654-3210", headers=hd).json() == {"deleted": True}
    assert client.delete("/v2/ads/accounts/987-654-3210", headers=hd).status_code == 404

    def refuse(token, customer, query):
        raise google_ads.GoogleAdsError("Google Ads has not been approved on the Google connection.")

    monkeypatch.setattr(google_ads, "search", refuse)
    failed = client.post("/v2/ads/pull", headers=hd)
    assert failed.status_code == 502 and "not been approved" in failed.json()["detail"]
    assert "not been approved" in client.get("/v2/ads/connection", headers=hd).json()["accounts"][0]["last_error"]


def test_diagnose_says_per_account_what_works_what_is_empty_and_what_is_refused(client, db, client_a, admin_user, team_user, monkeypatch):
    client_a.service_reporting = {"organiciq": True, "ad_accelerator": True}
    db.add(ClientAdsAccount(client_id=client_a.id, customer_id="1835262013", name="Aquaman", kind="ads"))
    db.add(ClientAdsAccount(client_id=client_a.id, customer_id="9876543210", name="Aquaman LSA", kind="lsa"))
    db.commit()
    seen = []

    def search(token, customer, query):
        seen.append((customer, query))
        if "FROM customer" in query and "customer_client" not in query:
            return [{"customer": {"id": customer, "descriptiveName": "Aquaman" if customer == "1835262013" else "Aquaman LSA", "currencyCode": "USD"}}]
        if "FROM campaign WHERE" in query:  # the Local Services campaign report
            return [{"segments": {"date": "2026-11-03"}, "campaign": {"name": "Local Services"}, "metrics": {"impressions": "40", "clicks": "7", "costMicros": "140000000"}}]
        if "FROM campaign" in query:
            kind = "SEARCH" if customer == "1835262013" else "LOCAL_SERVICES"
            return [{"campaign": {"id": "1", "name": "Pool", "status": "ENABLED", "advertisingChannelType": kind}}]
        if "local_services_lead" in query:
            return [{"localServicesLead": {"id": "9", "leadType": "PHONE_CALL", "leadStatus": "BOOKED", "leadCharged": True}}, {"localServicesLead": {"id": "10", "leadType": "MESSAGE", "leadStatus": "NEW"}}]
        if "FROM ad_group" in query:
            return [{"segments": {"date": "2026-11-03", "device": "MOBILE"}, "campaign": {"name": "Pool"}, "adGroup": {"name": "pool leak"}, "metrics": {"impressions": "100", "clicks": "5", "costMicros": "62500000"}}]
        if "search_term_view" in query:
            return []
        if "geographic_view" in query:
            raise google_ads.GoogleAdsError("PERMISSION_DENIED: not allowed to query geographic views")
        raise AssertionError(query)

    monkeypatch.setattr(google_ads, "access_token", lambda db: "token")
    monkeypatch.setattr(google_ads, "search", search)
    hd = client_header(client_a.id, admin_user.email)
    assert client.post("/v2/ads/diagnose", headers=client_header(client_a.id, team_user.email)).status_code == 403
    out = client.post("/v2/ads/diagnose", headers=hd).json()
    ads, lsa = out["accounts"]
    by = {c["name"]: c for c in ads["checks"]}
    assert by["The account"]["status"] == "ok" and by["The account"]["detail"] == "Aquaman (USD)"
    assert by["Campaigns"]["detail"] == "1 Search; 1 enabled" and "Local Services campaigns" not in by, "a search account is not asked for Local Services data"
    assert by["Daily performance"]["status"] == "ok" and "1 days, 100 impressions, 5 clicks, $62.50" in by["Daily performance"]["detail"] and by["Daily performance"]["sample"]
    assert by["What people searched for"]["status"] == "empty" and "no individual searches" in by["What people searched for"]["detail"].lower()
    assert by["Markets"]["status"] == "error" and by["Markets"]["detail"].startswith("PERMISSION_DENIED")
    lby = {c["name"]: c for c in lsa["checks"]}
    assert lby["Campaigns"]["detail"] == "1 Local Services; 1 enabled" and "Daily performance" not in lby, "an LSA account has no ad groups or devices"
    assert lby["Local Services campaigns"]["status"] == "ok" and "$140.00" in lby["Local Services campaigns"]["detail"]
    assert lby["Local Services leads"]["status"] == "ok" and lby["Local Services leads"]["detail"].startswith("2 leads: 1 phone call, 1 message; 1 booked, 1 new; 1 charged")

    def refuse(token, customer, query):
        raise google_ads.GoogleAdsError("PERMISSION_DENIED: only approved for test accounts")

    monkeypatch.setattr(google_ads, "search", refuse)
    refused = client.post("/v2/ads/diagnose", headers=hd).json()
    assert all(c["status"] == "error" and "test accounts" in c["detail"] for a in refused["accounts"] for c in a["checks"])
