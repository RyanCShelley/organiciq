from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.ads import AdsDaily, AdsSearchTerm
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
    assert {m["name"] for m in out["markets"]} == {"Brevard", "St Lucie"} and {d["name"] for d in out["devices"]} == {"Desktop", "Mobile"}
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
