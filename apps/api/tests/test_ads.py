from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.models.ads import AdsDaily, AdsNote, AdsSearchTerm
from tests.conftest import client_header


def h(client_a, admin_user):
    return client_header(client_a.id, admin_user.email)


def row(client, day, group="pool leak", market="Brevard", device="Desktop", imp=100, clk=5, cost="25.00", eligible=250, lost_budget=50, lost_rank=100, conv=0):
    return AdsDaily(client_id=client.id, date=day, campaign="Pool | 2026", ad_group=group, market=market, device=device, network="search", impressions=imp, clicks=clk, cost=Decimal(cost),
                    conversions=Decimal(conv), eligible_impressions=eligible, lost_budget=lost_budget, lost_rank=lost_rank, source="demo")


def seed(db, client):
    client.service_reporting = {"organiciq": True, "ad_accelerator": True}
    for i in range(30):  # October: the first half is capped by the budget, the second half is not
        day = date(2026, 10, 1) + timedelta(days=i)
        late = day >= date(2026, 10, 16)
        db.add(row(client, day, imp=200 if late else 100, clk=10 if late else 4, cost="50.00" if late else "20.00", eligible=400, lost_budget=0 if late else 150, lost_rank=100))
        db.add(row(client, day, group="slab leak", market="St Lucie", device="Mobile", imp=20, clk=1, cost="4.00", eligible=100, lost_budget=10, lost_rank=20, conv=1 if i == 3 else 0))
    for i in range(10):  # September, the month before
        db.add(row(client, date(2026, 9, 20) + timedelta(days=i), imp=50, clk=2, cost="10.00"))
    db.add(AdsSearchTerm(client_id=client.id, date=date(2026, 10, 5), term="pool leak detection near me", ad_group="pool leak", impressions=9, clicks=6, cost=Decimal("30.00")))
    db.add(AdsSearchTerm(client_id=client.id, date=date(2026, 10, 6), term="pool leak repair cost", ad_group="pool leak", impressions=4, clicks=2, cost=Decimal("11.00")))
    db.add(AdsNote(client_id=client.id, date=date(2026, 10, 16), text="Daily budget raised from $20 to $50.", created_by="jared@smamarketing.com"))
    db.commit()


def test_the_report_follows_the_order_of_the_client_report_and_splits_the_month_at_the_change(client, db, client_a, admin_user):
    seed(db, client_a)
    out = client.get("/v2/ads", params={"month": "2026-10"}, headers=h(client_a, admin_user)).json()
    t = out["totals"]
    assert out["enabled"] and out["available"] and t["impressions"] == 100 * 15 + 200 * 15 + 20 * 30 and t["clicks"] == 4 * 15 + 10 * 15 + 30
    assert t["cost"] == 20 * 15 + 50 * 15 + 4 * 30 and t["avg_cpc"] == round(t["cost"] / t["clicks"], 2) and out["previous"]["clicks"] == 20
    assert [w["week"] for w in out["weekly"]][0] == "Oct 1–4" and out["weekly"][-1]["week"] == "Oct 26–31"
    assert [g["name"] for g in out["groups"]] == ["pool leak", "slab leak"] and out["groups"][0]["cost"] > out["groups"][1]["cost"]
    assert {m["name"] for m in out["markets"]} == {"Brevard", "St Lucie"} and {d["name"] for d in out["devices"]} == {"Desktop", "Mobile"} and out["only_search"] is True
    assert [x["term"] for x in out["terms"]] == ["pool leak detection near me", "pool leak repair cost"] and "8 of the 94" not in out["terms_note"] and "of the" in out["terms_note"]
    split = out["split"]
    assert split["label"] == "Oct 16" and split["before"]["days"] == 15 and split["after"]["days"] == 15
    assert split["after"]["share"] > split["before"]["share"] and split["after"]["missed_budget"] < split["before"]["missed_budget"]
    assert split["after"]["clicks_per_day"] > split["before"]["clicks_per_day"]
    assert out["notes"][0]["text"].startswith("Daily budget") and any("After the Oct 16 changes" in s for s in out["summary"])
    assert any("conversion" in s for s in out["summary"])


def test_a_client_not_on_ads_accelerator_or_with_no_data_says_so_and_notes_can_be_added_and_removed(client, db, client_a, admin_user):
    hd = h(client_a, admin_user)
    assert client.get("/v2/ads", params={"month": "2026-10"}, headers=hd).json() == {"enabled": False, "month": "2026-10"}
    client_a.service_reporting = {"organiciq": True, "ad_accelerator": True}
    db.commit()
    nodata = client.get("/v2/ads", params={"month": "2026-10"}, headers=hd).json()
    assert nodata["enabled"] and nodata["available"] is False and "No Google Ads data" in nodata["reason"]
    made = client.post("/v2/ads/notes", json={"date": "2026-10-09", "text": "Added 12 excluded searches."}, headers=hd)
    assert made.status_code == 200 and made.json()["by"] == admin_user.email
    assert client.post("/v2/ads/notes", json={"date": "2026-10-09", "text": "x"}, headers=hd).status_code == 422
    assert client.delete(f"/v2/ads/notes/{made.json()['id']}", headers=hd).json() == {"deleted": True}
    assert client.get("/v2/ads", params={"month": "October"}, headers=hd).status_code == 422


def test_the_summary_is_the_few_numbers_the_review_shows(client, db, client_a, admin_user):
    seed(db, client_a)
    out = client.get("/v2/ads/summary", params={"month": "2026-10"}, headers=h(client_a, admin_user)).json()
    assert out["available"] and out["totals"]["clicks"] > 0 and out["previous"]["clicks"] == 20 and out["top_group"]["name"] == "pool leak" and out["top_term"]["term"] == "pool leak detection near me"
    assert out["text"].startswith("In October the ads showed")
