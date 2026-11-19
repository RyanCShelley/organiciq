"""Tier 4 E2E Tests: Realistic multi-step agency & client workflows (5 tests)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from tests.e2e_phase2.conftest import (
    admin_headers,
    api_headers,
    make_client,
    norm_key,
    seed_bing,
    seed_bucket,
    seed_competitor_kw,
    seed_crawl_issue,
    seed_crawl_page,
    seed_google_update,
    seed_gsc,
    seed_kw,
    seed_schema,
    seed_ser_ranking,
    seed_snapshot,
)

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


def test_t4_scenario_1_monthly_agency_review_and_visibility_check_workflow(client, db, client_a):
    base = f"https://{client_a.domain}"
    crawl = date.today()
    seed_crawl_page(db, client_a, base, "/", crawl, title="Home", desc="Home unique desc")
    seed_schema(db, client_a, base, "/", crawl, kind="Organization")
    seed_crawl_page(db, client_a, base, "/spf-1", crawl, title="Best Mineral SPF", desc="SPF 1 desc", dup_title=True)
    seed_crawl_page(db, client_a, base, "/spf-2", crawl, title="Best Mineral SPF", desc="SPF 2 desc", dup_title=True)

    b_sun = seed_bucket(db, client_a, "Sunscreen", sort_order=0)
    b_skin = seed_bucket(db, client_a, "Skincare", sort_order=1)
    for kw in ("mineral sunscreen", "zinc sunscreen", "daily spf", "sensitive skin lotion"):
        seed_kw(db, b_sun, client_a, kw)

    # Current & prior GSC + rising untracked hero
    for offset in (2, 9, 16, 23):
        day = START + timedelta(days=offset)
        prev_day = day - timedelta(days=28)
        seed_gsc(db, client_a, day, "mineral sunscreen", 200, 4.0, clicks=15, url=base + "/spf-1")
        seed_gsc(db, client_a, prev_day, "mineral sunscreen", 150, 8.0, clicks=8, url=base + "/spf-1")
        seed_gsc(db, client_a, day, "reef friendly zinc stick", 250, 6.0, clicks=18, url=base + "/zinc-stick")
        seed_gsc(db, client_a, prev_day, "reef friendly zinc stick", 40, 14.0, clicks=1, url=base + "/zinc-stick")

    # 4 weeks of Bing stats including a Friday week_start
    for w_day, imp, pos in (
        (date(2026, 10, 5), 40, "8.0"),
        (date(2026, 10, 12), 55, "6.0"),
        (date(2026, 10, 19), 70, "5.0"),
        (date(2026, 10, 23), 85, "4.0"),
    ):
        seed_bing(db, client_a, w_day, "mineral sunscreen", imp, clicks=5, avg_pos=Decimal(pos))
    seed_bing(db, client_a, date(2026, 9, 7), "mineral sunscreen", 100, clicks=4, avg_pos=Decimal("12.0"))

    seed_ser_ranking(db, client_a, date(2026, 10, 2), "k1", "mineral sunscreen", 9.0, ranking_url=base + "/spf-1")
    seed_ser_ranking(db, client_a, date(2026, 10, 27), "k1", "mineral sunscreen", 5.0, ranking_url=base + "/spf-1")
    seed_competitor_kw(
        db, client_a, "competitor.example", "reef friendly zinc stick", 2.0,
        date(2026, 10, 20), ranking_url="https://competitor.example/zinc-stick",
    )
    seed_google_update(
        db, update_id="core-2026-10", title="October 2026 Core Update",
        begin=date(2026, 10, 8), end=date(2026, 10, 18),
    )
    db.commit()

    # Step 1: Site Health
    sh = client.get("/v2/site-health", headers=admin_headers(client_a)).json()["data"]
    checks = {c["key"]: c for c in sh["seo"]["checks"]}
    assert "missing_titles" in checks and "duplicate_titles" in checks
    assert len(checks["duplicate_titles"]["duplicate_groups"]) == 1
    assert any(p["url"] == base + "/spf-1" and all(i["fix"].strip() for i in p["issues"]) for p in sh["by_page"])

    # Step 2: Search Visibility
    sv = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    ).json()
    assert sv["now"]["impressions"] > 0
    assert sv["bing_now"]["impressions"] == 250
    assert sv["bing_site"]["now"]["impressions"] == 250
    assert "mineral sunscreen" in [n.lower() for n in _mover_names(sv["bing_winners"])]
    assert len(sv["updates"]) == 1
    assert "reef friendly zinc stick" in {h["key"] for h in sv["unsung_heroes"]}

    # Step 3: Promote hero into Skincare bucket
    promote = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "reef friendly zinc stick", "bucket_id": str(b_skin.id)},
        headers=admin_headers(client_a),
    )
    assert promote.status_code in (200, 201)
    assert promote.json()["bucket_id"] == str(b_skin.id)

    # Step 4: Term drilldown
    term_detail = client.get(
        "/v2/search-visibility/term",
        params={"term": "reef friendly zinc stick", "from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert term_detail.status_code == 200
    td = term_detail.json()
    assert td["pages"][0]["url"] == base + "/zinc-stick"
    assert [c["domain"] for c in td["competitors"]] == ["competitor.example"]

    # Step 5: Log visibility check + patch review notes
    ann = client.post(
        "/v2/annotations",
        json={"date": "2026-10-25", "type": "visibility_check", "description": "October monthly review"},
        headers=admin_headers(client_a),
    )
    assert ann.status_code == 201
    ann_id = ann.json()["id"]
    patch = client.patch(
        f"/v2/annotations/{ann_id}",
        json={"notes": "Promoted zinc stick to Skincare after core update"},
        headers=admin_headers(client_a),
    )
    assert patch.status_code == 200

    sv_after = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    ).json()
    marker = next(a for a in sv_after["annotations"] if a["id"] == ann_id)
    assert marker["notes"] == "Promoted zinc stick to Skincare after core update"

    ann_list = client.get("/v2/annotations", headers=admin_headers(client_a)).json()["entries"]
    entry = next(e for e in ann_list if e["id"] == ann_id)
    assert entry["result"] == "not_yet_measured"
    assert entry["measure_from"] is None


def test_t4_scenario_2_new_client_onboarding_zero_watchlist_brand_aliases_and_bing_traction(client, db, tier):
    new_client = make_client(
        db, tier, "PureGlow Lab", domain="pureglowlab.example",
        brand_aliases=["pureglow", "pure glow lab"],
    )
    base = f"https://{new_client.domain}"
    crawl = date.today()
    seed_crawl_page(db, new_client, base, "/", crawl, title="", desc="PureGlow home")
    seed_crawl_page(db, new_client, base, "/missing-page", crawl, status=404, title="", desc="")
    seed_crawl_issue(db, new_client, crawl, "sitemap_missing")
    seed_crawl_issue(db, new_client, crawl, "ai_crawlers_blocked", raw={"agents": ["GPTBot"]})

    # Brand queries + non-brand rising queries
    for q in ("pureglow serum", "pure glow lab reviews", "bakuchiol night oil", "sensitive barrier cream"):
        seed_gsc(db, new_client, date(2026, 10, 12), q, 600, 6.0, clicks=30, url=base + "/")
        seed_gsc(db, new_client, date(2026, 9, 12), q, 100, 13.0, clicks=2, url=base + "/")
    seed_bing(db, new_client, date(2026, 10, 5), "bakuchiol night oil", 110, clicks=7, avg_pos=Decimal("5.0"))
    seed_bing(db, new_client, date(2026, 10, 12), "sensitive barrier cream", 90, clicks=4, avg_pos=Decimal("7.0"))
    db.commit()

    # Step 1: Initial visibility with zero watchlist
    sv1 = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(new_client),
    ).json()
    assert sv1["terms"] == []
    assert sv1["sources"]["has_bing"] is True
    assert sv1["bing_site"]["now"]["impressions"] == 200
    assert len(sv1["bing_series"]) >= 1
    hero_keys = {h["key"] for h in sv1["unsung_heroes"]}
    assert "pureglow serum" not in hero_keys
    assert "pure glow lab reviews" not in hero_keys
    assert {"bakuchiol night oil", "sensitive barrier cream"}.issubset(hero_keys)

    # Step 2: Promote two terms without bucket -> General created then reused
    p1 = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "bakuchiol night oil"},
        headers=admin_headers(new_client),
    )
    p2 = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "sensitive barrier cream"},
        headers=admin_headers(new_client),
    )
    assert p1.status_code in (200, 201) and p2.status_code in (200, 201)
    assert p1.json()["bucket_name"] == "General" and p1.json()["bucket_created"] is True
    assert p2.json()["bucket_name"] == "General" and p2.json()["bucket_created"] is False

    # Step 3: Re-fetch search visibility
    sv2 = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(new_client),
    ).json()
    assert {t["term"] for t in sv2["terms"]} == {"bakuchiol night oil", "sensitive barrier cream"}
    assert all(t["google"]["impressions"] == 600 and t["bing"]["impressions"] > 0 for t in sv2["terms"])
    assert {"bakuchiol night oil", "sensitive barrier cream"}.isdisjoint({h["key"] for h in sv2["unsung_heroes"]})

    # Step 4: Site Health
    sh = client.get("/v2/site-health", headers=admin_headers(new_client)).json()["data"]
    assert any(i["source"] == "seo" and i["key"] == "site_files" for i in sh["site_wide"])
    by_page_urls = {p["url"] for p in sh["by_page"]}
    assert {base + "/", base + "/missing-page", base + "/robots.txt"}.issubset(by_page_urls)

    # Step 5: Log onboarding visibility check
    ann = client.post(
        "/v2/annotations",
        json={"date": "2026-10-15", "type": "visibility_check", "description": "Onboarding baseline check"},
        headers=admin_headers(new_client),
    )
    assert ann.status_code == 201
    sv3 = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(new_client),
    ).json()
    assert any(a["id"] == ann.json()["id"] for a in sv3["annotations"])


def test_t4_scenario_3_post_migration_triage_multi_bucket_recovery_and_mixed_annotations(client, db, client_a):
    base = f"https://{client_a.domain}"
    crawl = date.today()
    for path in ("/mig-1", "/mig-2", "/mig-3"):
        seed_crawl_page(
            db, client_a, base, path, crawl,
            title=f"Migrated {path}", desc="Shared post migration description", dup_desc=True,
        )
    seed_crawl_page(db, client_a, base, "/old-path", crawl, status=301, redirects=3, title="Old", desc="Unique old")

    b_core = seed_bucket(db, client_a, "Core", sort_order=0)
    b_blog = seed_bucket(db, client_a, "Blog", sort_order=1)
    seed_kw(db, b_core, client_a, "core product")
    seed_kw(db, b_blog, client_a, "skincare guide")

    # Core drops in Google & Bing
    seed_gsc(db, client_a, date(2026, 9, 10), "core product", 400, 4.0, clicks=30)
    seed_gsc(db, client_a, date(2026, 10, 10), "core product", 300, 14.0, clicks=8)
    seed_bing(db, client_a, date(2026, 9, 7), "core product", 80, clicks=6, avg_pos=Decimal("3.0"))
    seed_bing(db, client_a, date(2026, 10, 5), "core product", 60, clicks=2, avg_pos=Decimal("12.0"))
    # Rising blog unsung hero
    seed_gsc(db, client_a, date(2026, 10, 12), "how to layer sunscreen", 750, 7.0, clicks=40, url=base + "/mig-1")
    seed_gsc(db, client_a, date(2026, 9, 12), "how to layer sunscreen", 120, 15.0, clicks=3, url=base + "/mig-1")
    db.commit()

    # Step 1: Duplicate descriptions (3 URLs) + merged SEO/GEO fixes
    sh = client.get("/v2/site-health", headers=admin_headers(client_a)).json()["data"]
    checks = {c["key"]: c for c in sh["seo"]["checks"]}
    dd_groups = checks["duplicate_descriptions"]["duplicate_groups"]
    assert len(dd_groups) == 1 and dd_groups[0]["count"] == 3
    assert set(dd_groups[0]["urls"]) == {base + "/mig-1", base + "/mig-2", base + "/mig-3"}
    by_page = {p["url"]: p for p in sh["by_page"]}
    assert by_page[base + "/mig-1"]["seo_count"] >= 1 and by_page[base + "/mig-1"]["geo_count"] >= 1

    # Step 2: Core bucket filter isolates declines
    sv_core = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat(), "bucket": str(b_core.id)},
        headers=admin_headers(client_a),
    ).json()
    assert "core product" in [n.lower() for n in _mover_names(sv_core["losers"])]
    assert "core product" in [n.lower() for n in _mover_names(sv_core["bing_losers"])]

    # Step 3: Create Q4 Recovery bucket and add rising blog hero
    rec = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "how to layer sunscreen", "bucket_name": "Q4 Recovery"},
        headers=admin_headers(client_a),
    )
    assert rec.status_code in (200, 201)
    assert rec.json()["bucket_name"] == "Q4 Recovery"
    assert rec.json()["bucket_created"] is True

    # Step 4: Create both technical_change (measured) and visibility_check (unmeasured)
    tech = client.post(
        "/v2/annotations",
        json={"date": "2026-10-14", "type": "technical_change", "description": "Fixed migration redirect chains"},
        headers=admin_headers(client_a),
    )
    vc = client.post(
        "/v2/annotations",
        json={"date": "2026-10-20", "type": "visibility_check", "description": "Post-migration visibility check"},
        headers=admin_headers(client_a),
    )
    assert tech.status_code == 201 and vc.status_code == 201

    # Step 5: Verify chart markers & annotation measurement semantics
    sv_all = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    ).json()
    assert {a["id"] for a in sv_all["annotations"]} == {tech.json()["id"], vc.json()["id"]}

    entries = {e["id"]: e for e in client.get("/v2/annotations", headers=admin_headers(client_a)).json()["entries"]}
    assert entries[tech.json()["id"]]["measure_from"] == "2026-10-14"
    assert entries[tech.json()["id"]]["measure_to"] is not None
    assert entries[vc.json()["id"]]["measure_from"] is None
    assert entries[vc.json()["id"]]["measure_to"] is None


def test_t4_scenario_4_consulting_historical_snapshot_and_annotation_edit_delete_lifecycle(client, db, client_a):
    base = f"https://{client_a.domain}"
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
            "crawl": {"date": prev_date.isoformat(), "pages": 2, "limit": 500, "hit_limit": False},
            "seo": {
                "score": 82,
                "grade": "B",
                "checks": [
                    {"key": "titles", "label": "Titles", "weight": 15, "score": 50, "affected": 1, "total": 2, "urls": [base + "/old"]},
                    {"key": "descriptions", "label": "Descriptions", "weight": 10, "score": 100, "affected": 0, "total": 2, "urls": []},
                ],
                "pages": 2,
            },
            "geo": {
                "score": 70,
                "grade": "C-",
                "partial": True,
                "answers": None,
                "signals": [
                    {"key": "entity", "label": "Entity clarity", "weight": 10, "score": 50, "measured": True, "affected": 1, "items": [{"text": "No about page", "url": None}]},
                ],
            },
            "previous": None,
            "changes": [],
        },
    )
    seed_crawl_page(db, client_a, base, "/", today, title="Home", desc="Home desc")
    seed_schema(db, client_a, base, "/", today)

    bucket = seed_bucket(db, client_a, "Consulting")
    seed_kw(db, bucket, client_a, "organic moisturizer")
    # 8 Mondays: Sep 7, 14, 21, 28, Oct 5, 12, 19, 26
    for i in range(8):
        w = date(2026, 9, 7) + timedelta(days=7 * i)
        seed_gsc(db, client_a, w, "organic moisturizer", 120 + i * 10, 6.0, clicks=8)
        seed_bing(db, client_a, w, "organic moisturizer", 40 + i * 5, clicks=3, avg_pos=Decimal("7.0"))
    db.commit()

    algo = client.post(
        "/v2/annotations",
        json={"date": "2026-09-18", "type": "algorithm_event", "description": "September spam update"},
        headers=admin_headers(client_a),
    )
    assert algo.status_code == 201

    # Step 1: Historical snapshot backfill + current month delta
    sh_prev = client.get("/v2/site-health", params={"month": prev_month}, headers=admin_headers(client_a)).json()["data"]
    assert sh_prev["locked"] is True and sh_prev["seo"]["score"] == 82
    assert sh_prev["by_page"] and sh_prev["site_wide"]

    sh_cur = client.get("/v2/site-health", params={"month": cur_month}, headers=admin_headers(client_a)).json()["data"]
    assert sh_cur["previous"]["month"] == prev_month
    assert sh_cur["previous"]["seo"] == 82

    # Step 2: 8 Monday-aligned weeks across Sep 7 .. Oct 28
    sv = client.get(
        "/v2/search-visibility",
        params={"from": "2026-09-07", "to": "2026-10-28"},
        headers=admin_headers(client_a),
    ).json()
    assert len(sv["weeks"]) == 8
    assert [b["week"] for b in sv["bing_series"]] == sv["weeks"]
    assert [s["week"] for s in sv["series"]] == sv["weeks"]
    assert any(a["id"] == algo.json()["id"] for a in sv["annotations"])

    # Step 3 & 4: Create 2 visibility checks, edit one, delete the other
    vc1 = client.post(
        "/v2/annotations",
        json={"date": "2026-10-10", "type": "visibility_check", "description": "Check A"},
        headers=admin_headers(client_a),
    )
    vc2 = client.post(
        "/v2/annotations",
        json={"date": "2026-10-11", "type": "visibility_check", "description": "Duplicate Check B"},
        headers=admin_headers(client_a),
    )
    assert vc1.status_code == 201 and vc2.status_code == 201
    vc1_id, vc2_id = vc1.json()["id"], vc2.json()["id"]

    assert client.patch(
        f"/v2/annotations/{vc1_id}",
        json={"notes": "Confirmed steady recovery across 8 weeks"},
        headers=admin_headers(client_a),
    ).status_code == 200
    assert client.delete(f"/v2/annotations/{vc2_id}", headers=admin_headers(client_a)).status_code == 200

    sv_end = client.get(
        "/v2/search-visibility",
        params={"from": "2026-09-07", "to": "2026-10-28"},
        headers=admin_headers(client_a),
    ).json()
    ann_ids = {a["id"] for a in sv_end["annotations"]}
    assert vc1_id in ann_ids and vc2_id not in ann_ids
    kept = next(a for a in sv_end["annotations"] if a["id"] == vc1_id)
    assert kept["notes"] == "Confirmed steady recovery across 8 weeks"


def test_t4_scenario_5_multi_tenant_staff_rbac_isolation_and_idempotent_curation(
    client, db, client_a, client_b, admin_user, team_user
):
    crawl = date.today()
    seed_crawl_page(db, client_a, "https://clienta.example", "/a-page", crawl, title="", desc="A desc")
    seed_crawl_page(db, client_b, "https://clientb.example", "/b-page", crawl, title="B Title", desc="B desc")
    seed_schema(db, client_b, "https://clientb.example", "/b-page", crawl)

    b_a = seed_bucket(db, client_a, "Client A Core")
    seed_kw(db, b_a, client_a, "alpha serum")
    b_b = seed_bucket(db, client_b, "Client B Core")
    seed_kw(db, b_b, client_b, "beta lotion")

    seed_gsc(db, client_a, date(2026, 10, 10), "alpha serum", 200, 5.0)
    seed_gsc(db, client_a, date(2026, 10, 12), "alpha unsung hero", 500, 6.0, clicks=25)
    seed_gsc(db, client_a, date(2026, 9, 12), "alpha unsung hero", 100, 14.0, clicks=3)
    seed_bing(db, client_a, date(2026, 10, 5), "alpha serum", 120, clicks=9, avg_pos=Decimal("4.0"))

    seed_gsc(db, client_b, date(2026, 10, 10), "beta lotion", 150, 7.0)
    db.commit()

    team_a = api_headers(client_a.id, team_user.email)
    team_b = api_headers(client_b.id, team_user.email)
    adm_a = api_headers(client_a.id, admin_user.email)
    adm_b = api_headers(client_b.id, admin_user.email)

    # Step 1: team_user succeeds on assigned client_a
    assert client.get("/v2/site-health", headers=team_a).status_code == 200
    assert client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=team_a,
    ).status_code == 200
    kw_resp = client.post("/v2/watchlist/keywords", json={"keyword": "alpha unsung hero"}, headers=team_a)
    assert kw_resp.status_code in (200, 201) and kw_resp.json()["created"] is True
    ann_resp = client.post(
        "/v2/annotations",
        json={"date": "2026-10-15", "type": "visibility_check", "description": "Client A team check"},
        headers=team_a,
    )
    assert ann_resp.status_code == 201

    # Step 2: team_user forbidden on unassigned client_b
    assert client.get("/v2/site-health", headers=team_b).status_code == 403
    assert client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=team_b,
    ).status_code == 403
    assert client.post("/v2/watchlist/keywords", json={"keyword": "forbidden"}, headers=team_b).status_code == 403
    assert client.post(
        "/v2/annotations",
        json={"date": "2026-10-15", "type": "visibility_check", "description": "Forbidden check"},
        headers=team_b,
    ).status_code == 403

    # Step 3: admin_user reading client_b sees zero leakage from client_a
    sv_b = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=adm_b,
    ).json()
    assert [t["term"] for t in sv_b["terms"]] == ["beta lotion"]
    assert sv_b["sources"]["has_bing"] is False
    assert sv_b["annotations"] == []
    assert all("alpha" not in h["key"] for h in sv_b["unsung_heroes"])
    assert client.get("/v2/annotations", headers=adm_b).json()["entries"] == []
    sh_b = client.get("/v2/site-health", headers=adm_b).json()["data"]
    assert all("clienta.example" not in p["url"] for p in sh_b["by_page"])

    # Step 4: admin_user idempotent retry with mixed case & extra spaces on client_a
    retry = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "  ALPHA   Unsung  HERO "},
        headers=adm_a,
    )
    assert retry.status_code in (200, 201)
    assert retry.json()["created"] is False
    assert retry.json()["id"] == kw_resp.json()["id"]
    assert retry.json()["keyword_key"] == norm_key("alpha unsung hero")
    assert client.get("/v2/watchlist", headers=adm_a).json()["keyword_count"] == 2
