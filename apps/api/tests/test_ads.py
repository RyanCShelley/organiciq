from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.ads import AdsDaily, AdsMarketDaily, AdsSearchTerm
from tests.conftest import client_header


def h(client_a, admin_user):
    return client_header(client_a.id, admin_user.email)


def row(client, day, group="pool leak", market="Brevard", device="Desktop", imp=100, clk=5, cost="25.00", eligible=250, conv=0):
    return AdsDaily(client_id=client.id, date=day, campaign="Pool | 2026", ad_group=group, market=market, device=device, network="search", impressions=imp, clicks=clk, cost=Decimal(cost),
                    conversions=Decimal(conv), eligible_impressions=eligible, source="demo")


def seed(db, client):
    client.service_reporting = {"organiciq": True, "ad_accelerator": True}
    for i in range(30):
        day = date(2026, 10, 1) + timedelta(days=i)
        db.add(row(client, day, imp=100, clk=4, cost="20.00", eligible=400))
        db.add(row(client, day, group="slab leak", market="St Lucie", device="Mobile", imp=20, clk=1, cost="4.00", eligible=100, conv=1 if i == 3 else 0))
    for i in range(30):  # markets are kept apart from ad groups and devices
        day = date(2026, 10, 1) + timedelta(days=i)
        db.add(AdsMarketDaily(client_id=client.id, date=day, campaign="Pool | 2026", market="Brevard County", impressions=90, clicks=4, cost=Decimal("20.00"), source="demo"))
        db.add(AdsMarketDaily(client_id=client.id, date=day, campaign="Pool | 2026", market="St Lucie County", impressions=30, clicks=1, cost=Decimal("4.00"), source="demo"))
    for i in range(10):  # September, the month before
        db.add(row(client, date(2026, 9, 20) + timedelta(days=i), imp=50, clk=2, cost="10.00"))
    db.add(AdsSearchTerm(client_id=client.id, date=date(2026, 10, 5), term="pool leak detection near me", ad_group="pool leak", impressions=9, clicks=6, cost=Decimal("30.00")))
    db.add(AdsSearchTerm(client_id=client.id, date=date(2026, 10, 6), term="pool leak repair cost", ad_group="pool leak", impressions=4, clicks=2, cost=Decimal("11.00")))
    db.commit()


def test_the_report_is_the_numbers_in_the_order_of_the_page(client, db, client_a, admin_user):
    seed(db, client_a)
    out = client.get("/v2/ads", params={"month": "2026-10"}, headers=h(client_a, admin_user)).json()
    t = out["totals"]
    assert out["enabled"] and out["available"] and t["impressions"] == 100 * 30 + 20 * 30 and t["clicks"] == 4 * 30 + 30
    assert t["cost"] == 20 * 30 + 4 * 30 and t["avg_cpc"] == round(t["cost"] / t["clicks"], 2) and t["ctr"] == round(100 * t["clicks"] / t["impressions"], 2)
    assert t["share"] == round(100 * t["impressions"] / (400 * 30 + 100 * 30), 1) and t["conversions"] == 1 and out["previous"]["clicks"] == 20
    assert out["weekly"][0]["week"] == "Oct 1–4" and out["weekly"][-1]["week"] == "Oct 26–31"
    assert [g["name"] for g in out["groups"]] == ["pool leak", "slab leak"] and out["groups"][0]["cost"] > out["groups"][1]["cost"]
    assert [m["name"] for m in out["markets"]] == ["Brevard County", "St Lucie County"] and out["markets"][0]["clicks"] == 120 and out["markets"][0]["share"] is None
    assert {m["name"] for m in out["markets"]} == {"Brevard County", "St Lucie County"} and {d["name"] for d in out["devices"]} == {"Desktop", "Mobile"}
    assert [x["term"] for x in out["terms"]] == ["pool leak detection near me", "pool leak repair cost"]
    assert not {"summary", "notes", "split", "terms_note"} & set(out), "numbers only: no written commentary"


def test_a_client_not_on_ads_accelerator_or_with_no_data_says_so_and_a_bad_month_is_refused(client, db, client_a, admin_user):
    hd = h(client_a, admin_user)
    assert client.get("/v2/ads", params={"month": "2026-10"}, headers=hd).json() == {"enabled": False, "month": "2026-10"}
    client_a.service_reporting = {"organiciq": True, "ad_accelerator": True}
    db.commit()
    nodata = client.get("/v2/ads", params={"month": "2026-10"}, headers=hd).json()
    assert nodata["enabled"] and nodata["available"] is False and "No Google Ads data" in nodata["reason"]
    assert client.get("/v2/ads", params={"month": "October"}, headers=hd).status_code == 422


def test_the_summary_is_the_month_beside_the_month_before(client, db, client_a, admin_user):
    seed(db, client_a)
    out = client.get("/v2/ads/summary", params={"month": "2026-10"}, headers=h(client_a, admin_user)).json()
    assert out["available"] and out["totals"]["clicks"] == 150 and out["previous"]["clicks"] == 20 and set(out) == {"enabled", "available", "month", "source", "totals", "previous"}


def test_local_services_leads_are_counted_by_type_status_and_week_with_what_the_account_spent(client, db, client_a, admin_user):
    from app.models.ads import AdsLsaLead, ClientAdsAccount

    seed(db, client_a)
    db.add(ClientAdsAccount(client_id=client_a.id, customer_id="6589596576", name="LSA - Aquaman", kind="lsa"))
    for i in range(10):
        db.add(AdsDaily(client_id=client_a.id, account_id="6589596576", date=date(2026, 10, 5) + timedelta(days=i), campaign="Local Services", ad_group="Local Services", impressions=40, clicks=7, cost=Decimal("50.00"), source="google_ads"))
    leads = [("1", date(2026, 10, 2), "PHONE_CALL", "BOOKED", True), ("2", date(2026, 10, 3), "PHONE_CALL", "DECLINED", False), ("3", date(2026, 10, 9), "MESSAGE", "ACTIVE", True),
             ("4", date(2026, 10, 20), "PHONE_CALL", "DECLINED", True), ("5", date(2026, 9, 28), "PHONE_CALL", "BOOKED", True)]
    for lead_id, day, kind, status, charged in leads:
        db.add(AdsLsaLead(client_id=client_a.id, account_id="6589596576", lead_id=lead_id, date=day, lead_type=kind, lead_status=status, charged=charged))
    db.commit()
    out = client.get("/v2/ads", params={"month": "2026-10"}, headers=h(client_a, admin_user)).json()
    lsa = out["lsa"]
    assert lsa["leads"] == 4 and lsa["charged"] == 3 and lsa["previous"] == {"leads": 1, "charged": 1}
    assert lsa["cost"] == 500.0 and lsa["cost_per_charged_lead"] == round(500 / 3, 2) and lsa["clicks"] == 70 and lsa["impressions"] == 400
    assert lsa["by_status"] == [{"name": "Declined", "leads": 2}, {"name": "Active", "leads": 1}, {"name": "Booked", "leads": 1}]
    assert lsa["by_type"] == [{"name": "Phone call", "leads": 3}, {"name": "Message", "leads": 1}]
    assert [w["leads"] for w in lsa["weekly"]] == [2, 1, 1] and lsa["weekly"][0]["week"] == "Oct 1–4"
    assert lsa["leads"] + 0 == sum(s["leads"] for s in lsa["by_status"])
