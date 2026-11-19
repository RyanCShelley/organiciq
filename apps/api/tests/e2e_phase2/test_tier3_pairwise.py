"""Tier 3 E2E Tests: Pairwise cross-feature combination tests across R1–R5 (8 tests)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from tests.e2e_phase2.conftest import (
    admin_headers,
    norm_key,
    seed_bing,
    seed_bucket,
    seed_crawl_issue,
    seed_crawl_page,
    seed_gsc,
    seed_internal_link,
    seed_kw,
    seed_schema,
    seed_snapshot,
)

BASE = "https://shop.example"
START = date(2026, 10, 1)
END = date(2026, 10, 28)


def _mover_names(items: list) -> list[str]:
    names: list[str] = []
    for item in items:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            names.append(str(item.get("term") or item.get("query") or ""))
    return names


def test_t3_r1_r2_site_health_meta_split_duplicate_groups_and_by_page_merge(client, db, client_a):
    crawl = date.today()
    seed_crawl_page(db, client_a, BASE, "/", crawl, title="Home", desc="Home desc")
    seed_schema(db, client_a, BASE, "/", crawl, kind="Organization")
    seed_crawl_page(db, client_a, BASE, "/p1", crawl, title="Same Title", desc="Desc P1", dup_title=True)
    seed_crawl_page(db, client_a, BASE, "/p2", crawl, title="Same Title", desc="Desc P2", dup_title=True)
    seed_crawl_page(db, client_a, BASE, "/p3", crawl, title="", desc="")
    seed_crawl_page(db, client_a, BASE, "/p4", crawl, title="Title P4", desc="Same Desc", dup_desc=True)
    seed_crawl_page(db, client_a, BASE, "/p5", crawl, title="Title P5", desc="Same Desc", dup_desc=True)
    seed_crawl_page(db, client_a, BASE, "/gone", crawl, status=404, title="Gone", desc="Gone desc")
    seed_internal_link(db, client_a, crawl, BASE + "/", BASE + "/gone")
    seed_crawl_issue(db, client_a, crawl, "ai_crawlers_blocked", normalized_url=None, raw={"agents": ["GPTBot"]})
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    data = resp.json()["data"]

    checks = {c["key"]: c for c in data["seo"]["checks"]}
    assert sum(c["weight"] for c in data["seo"]["checks"]) == 100
    assert checks["missing_titles"]["affected"] == 1
    assert checks["duplicate_titles"]["affected"] == 2
    assert {norm_key(g["text"]): set(g["urls"]) for g in checks["duplicate_titles"]["duplicate_groups"]} == {
        "same title": {BASE + "/p1", BASE + "/p2"}
    }
    assert {norm_key(g["text"]): set(g["urls"]) for g in checks["duplicate_descriptions"]["duplicate_groups"]} == {
        "same desc": {BASE + "/p4", BASE + "/p5"}
    }

    by_page = {p["url"]: p for p in data["by_page"]}
    p3 = by_page[BASE + "/p3"]
    assert p3["seo_count"] >= 2
    assert p3["geo_count"] >= 1
    assert p3["issue_count"] == p3["seo_count"] + p3["geo_count"]
    assert p3["highest_severity"] in {"high", "medium", "low"}

    sw_urls_absent = all(isinstance(i, dict) and "url" not in i for i in data["site_wide"])
    assert sw_urls_absent
    assert any(i["source"] == "geo" and i["key"] == "entity" for i in data["site_wide"])


def test_t3_r1_r2_legacy_snapshot_backfill_and_current_month_comparison(client, db, client_a):
    today = date.today()
    cur_month = today.strftime("%Y-%m")
    prev_date = today.replace(day=1) - timedelta(days=1)
    prev_month = prev_date.strftime("%Y-%m")

    seed_snapshot(
        db,
        client_a,
        prev_month,
        prev_date,
        {
            "month": prev_month,
            "crawl_date": prev_date.isoformat(),
            "crawl": {"date": prev_date.isoformat(), "pages": 3, "limit": 500, "hit_limit": False},
            "seo": {
                "score": 76,
                "grade": "C+",
                "checks": [
                    {"key": "titles", "label": "Titles", "weight": 15, "score": 67, "affected": 1, "total": 3, "urls": [BASE + "/old-dup"]},
                    {"key": "descriptions", "label": "Descriptions", "weight": 10, "score": 100, "affected": 0, "total": 3, "urls": []},
                    {"key": "site_files", "label": "Robots & sitemap", "weight": 10, "score": 60, "affected": 1, "total": 1, "urls": ["no sitemap found"]},
                ],
                "pages": 3,
            },
            "geo": {
                "score": 70,
                "grade": "C-",
                "partial": True,
                "answers": None,
                "signals": [
                    {"key": "schema", "label": "Structured data", "weight": 10, "score": 40, "measured": True, "affected": 1, "items": [{"text": "No schema on /home", "url": BASE + "/home"}]},
                    {"key": "entity", "label": "Entity clarity", "weight": 10, "score": 50, "measured": True, "affected": 1, "items": [{"text": "No about page", "url": None}]},
                ],
            },
            "previous": None,
            "changes": [],
        },
    )

    seed_crawl_page(db, client_a, BASE, "/home", today, title="Home", desc="Home desc")
    seed_schema(db, client_a, BASE, "/home", today)
    seed_crawl_page(db, client_a, BASE, "/about", today, title="About", desc="About desc")
    seed_crawl_page(db, client_a, BASE, "/contact", today, title="Contact", desc="Contact desc")
    db.commit()

    r_prev = client.get("/v2/site-health", params={"month": prev_month}, headers=admin_headers(client_a))
    assert r_prev.status_code == 200
    prev_data = r_prev.json()["data"]
    assert prev_data["locked"] is True
    assert prev_data["seo"]["score"] == 76
    assert prev_data["by_page"] and prev_data["site_wide"]
    for item in [iss for p in prev_data["by_page"] for iss in p["issues"]] + prev_data["site_wide"]:
        assert item["problem"].strip() and item["fix"].strip()
        assert item["severity"] in {"high", "medium", "low"}

    r_cur = client.get("/v2/site-health", params={"month": cur_month}, headers=admin_headers(client_a))
    assert r_cur.status_code == 200
    cur_data = r_cur.json()["data"]
    assert cur_data["previous"]["month"] == prev_month
    assert cur_data["previous"]["seo"] == 76


def test_t3_r3_r4_promoting_unsung_hero_updates_bing_watchlist_kpis(client, db, client_a):
    core = seed_bucket(db, client_a, "Core")
    seed_kw(db, core, client_a, "natural sunscreen")

    seed_gsc(db, client_a, date(2026, 10, 10), "zinc lotion", 500, 8.0, clicks=25)
    seed_gsc(db, client_a, date(2026, 9, 10), "zinc lotion", 100, 12.0, clicks=4)
    seed_bing(db, client_a, date(2026, 10, 5), "zinc lotion", 90, clicks=6, avg_pos=Decimal("4.0"))
    seed_bing(db, client_a, date(2026, 9, 7), "zinc lotion", 40, clicks=2, avg_pos=Decimal("9.0"))
    db.commit()

    before = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    ).json()
    assert "zinc lotion" in {h["key"] for h in before["unsung_heroes"]}
    assert before["bing_now"]["impressions"] == 0
    assert before["bing_site"]["now"]["impressions"] == 90
    assert before["sources"]["bing_terms"] == 0
    assert before["sources"]["bing_site_terms"] == 1

    add = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "zinc lotion"},
        headers=admin_headers(client_a),
    )
    assert add.status_code in (200, 201)

    after = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    ).json()
    assert "zinc lotion" not in {h["key"] for h in after["unsung_heroes"]}
    term = next(t for t in after["terms"] if t["term"].lower() == "zinc lotion")
    assert term["bing"]["impressions"] == 90
    assert term["bing"]["position"] == 4.0
    assert term["bing"]["position_before"] == 9.0
    assert term["bing"]["move"] == 5.0
    assert after["bing_now"]["impressions"] == 90
    assert after["sources"]["bing_terms"] == 1
    assert "zinc lotion" in [n.lower() for n in _mover_names(after["bing_winners"])]


def test_t3_r3_r5_unsung_hero_promotion_and_visibility_check_marker(client, db, client_a):
    seed_gsc(db, client_a, date(2026, 10, 12), "reef safe sunscreen", 600, 6.0, clicks=35)
    seed_gsc(db, client_a, date(2026, 9, 12), "reef safe sunscreen", 100, 13.0, clicks=3)
    db.commit()

    sv1 = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    ).json()
    assert "reef safe sunscreen" in {h["key"] for h in sv1["unsung_heroes"]}

    add = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "reef safe sunscreen"},
        headers=admin_headers(client_a),
    )
    assert add.status_code in (200, 201)
    assert add.json()["bucket_name"] == "General"
    assert add.json()["bucket_created"] is True

    ann = client.post(
        "/v2/annotations",
        json={
            "date": "2026-10-16",
            "type": "visibility_check",
            "description": "Promoted reef safe sunscreen",
        },
        headers=admin_headers(client_a),
    )
    assert ann.status_code == 201

    sv2 = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    ).json()
    assert any(b["name"] == "General" for b in sv2["buckets"])
    assert any(t["term"].lower() == "reef safe sunscreen" for t in sv2["terms"])
    assert "reef safe sunscreen" not in {h["key"] for h in sv2["unsung_heroes"]}
    assert any(
        a["type"] == "visibility_check" and a["date"] == "2026-10-16"
        for a in sv2["annotations"]
    )


def test_t3_r4_r5_bing_friday_series_and_mixed_annotations_range_alignment(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Core")
    seed_kw(db, bucket, client_a, "mineral spf")
    seed_gsc(db, client_a, date(2026, 10, 7), "mineral spf", 150, 5.0)
    seed_gsc(db, client_a, date(2026, 10, 14), "mineral spf", 180, 4.0)
    seed_bing(db, client_a, date(2026, 10, 9), "mineral spf", 50, clicks=3, avg_pos=Decimal("6.0"))
    seed_bing(db, client_a, date(2026, 10, 16), "mineral spf", 80, clicks=5, avg_pos=Decimal("4.0"))
    seed_bing(db, client_a, date(2026, 9, 11), "mineral spf", 40, clicks=1, avg_pos=Decimal("9.0"))
    db.commit()

    for d, t, desc in (
        ("2026-09-20", "visibility_check", "Out of range check"),
        ("2026-10-12", "visibility_check", "October visibility check"),
        ("2026-10-18", "technical_change", "Updated canonical tags"),
    ):
        r = client.post(
            "/v2/annotations",
            json={"date": d, "type": t, "description": desc},
            headers=admin_headers(client_a),
        )
        assert r.status_code == 201

    sv = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    ).json()
    assert sv["weeks"] == ["2026-10-05", "2026-10-12"]
    assert [b["week"] for b in sv["bing_series"]] == ["2026-10-05", "2026-10-12"]
    assert sv["bing_series"][0]["impressions"] == 50
    assert sv["bing_series"][1]["impressions"] == 80
    assert {(a["date"], a["type"]) for a in sv["annotations"]} == {
        ("2026-10-12", "visibility_check"),
        ("2026-10-18", "technical_change"),
    }


def test_t3_r3_r4_bucket_filter_narrows_terms_and_bing_watchlist_while_preserving_bing_site(client, db, client_a):
    b_spf = seed_bucket(db, client_a, "SPF", sort_order=0)
    b_oils = seed_bucket(db, client_a, "Oils", sort_order=1)
    seed_kw(db, b_spf, client_a, "mineral spf")
    seed_kw(db, b_oils, client_a, "face oil")

    seed_gsc(db, client_a, date(2026, 10, 10), "organic serum", 700, 6.0, clicks=30)
    seed_gsc(db, client_a, date(2026, 9, 10), "organic serum", 100, 14.0, clicks=3)
    seed_bing(db, client_a, date(2026, 10, 5), "mineral spf", 40, clicks=3, avg_pos=Decimal("5.0"))
    seed_bing(db, client_a, date(2026, 10, 5), "face oil", 100, clicks=8, avg_pos=Decimal("4.0"))
    seed_bing(db, client_a, date(2026, 10, 5), "sunblock", 60, clicks=4, avg_pos=Decimal("7.0"))
    db.commit()

    sv = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat(), "bucket": str(b_spf.id)},
        headers=admin_headers(client_a),
    ).json()
    assert [t["term"] for t in sv["terms"]] == ["mineral spf"]
    assert sv["bing_now"]["impressions"] == 40
    assert sv["sources"]["bing_terms"] == 1
    assert sv["bing_site"]["now"]["impressions"] == 200
    assert sv["sources"]["bing_site_terms"] == 3
    assert len(sv["buckets"]) == 2
    assert "organic serum" in {h["key"] for h in sv["unsung_heroes"]}


def test_t3_r2_r3_site_health_by_page_and_unsung_hero_on_same_url(client, db, client_a):
    crawl = date.today()
    target_url = seed_crawl_page(
        db, client_a, BASE, "/mineral-spf", crawl,
        title="Mineral SPF", desc="",
    )
    seed_gsc(db, client_a, date(2026, 10, 10), "reef friendly spf", 800, 9.0, clicks=30, url=target_url)
    seed_gsc(db, client_a, date(2026, 9, 10), "reef friendly spf", 150, 15.0, clicks=4, url=target_url)
    db.commit()

    sh = client.get("/v2/site-health", headers=admin_headers(client_a)).json()["data"]
    page = next(p for p in sh["by_page"] if p["url"] == target_url)
    keys = {(i["source"], i["key"]) for i in page["issues"]}
    assert ("seo", "missing_descriptions") in keys
    assert ("seo", "schema") in keys
    assert ("geo", "faq") in keys
    assert all(i["fix"].strip() for i in page["issues"])

    sv = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    ).json()
    hero = next(h for h in sv["unsung_heroes"] if h["key"] == "reef friendly spf")
    assert hero["page"] == target_url


def test_t3_r1_r2_r5_site_health_audit_logged_as_visibility_check_annotation(client, db, client_a):
    crawl = date.today()
    seed_crawl_page(db, client_a, BASE, "/dup1", crawl, title="Dup", desc="Desc 1", dup_title=True)
    seed_crawl_page(db, client_a, BASE, "/dup2", crawl, title="Dup", desc="Desc 2", dup_title=True)
    seed_crawl_page(db, client_a, BASE, "/dead", crawl, status=404, title="Dead", desc="Dead desc")
    db.commit()

    sh1 = client.get("/v2/site-health", headers=admin_headers(client_a)).json()["data"]
    assert any(p["url"] == BASE + "/dup1" for p in sh1["by_page"])

    ann = client.post(
        "/v2/annotations",
        json={
            "date": "2026-10-21",
            "type": "visibility_check",
            "page": BASE + "/dup1",
            "description": "Logged site health title check",
        },
        headers=admin_headers(client_a),
    )
    assert ann.status_code == 201
    ann_id = ann.json()["id"]

    anns = client.get("/v2/annotations", headers=admin_headers(client_a)).json()["entries"]
    entry = next(e for e in anns if e["id"] == ann_id)
    assert entry["result"] == "not_yet_measured"
    assert entry["page"] == BASE + "/dup1"

    sv = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    ).json()
    assert any(a["id"] == ann_id and a["type"] == "visibility_check" for a in sv["annotations"])

    sh2 = client.get("/v2/site-health", headers=admin_headers(client_a)).json()["data"]
    assert sh2["seo"]["score"] == sh1["seo"]["score"]
