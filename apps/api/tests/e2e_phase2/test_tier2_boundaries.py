"""Tier 2 E2E Tests: Boundary, edge, negative, and RBAC cases across F1–F5 (29 tests)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.models.user import UserRole
from tests.e2e_phase2.conftest import (
    admin_headers,
    api_headers,
    make_user,
    norm_key,
    seed_bing,
    seed_bucket,
    seed_crawl_issue,
    seed_crawl_page,
    seed_gsc,
    seed_kw,
    seed_llm_run,
    seed_schema,
    seed_snapshot,
)

BASE = "https://shop.example"
START = date(2026, 10, 1)
END = date(2026, 10, 28)


# ── F1: Site Health — Meta Separation & Grouping Boundaries (6) ──────────────


def test_f1_t2_empty_crawl_returns_null_data(client, client_a):
    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    assert resp.json() == {"month": None, "months": [], "crawls": [], "compare_to": None, "data": None}


def test_f1_t2_pagination_urls_excluded_from_missing_and_duplicate_meta(client, db, client_a):
    crawl = date.today()
    seed_crawl_page(db, client_a, BASE, "/", crawl, title="Home", desc="Home unique desc")
    seed_crawl_page(db, client_a, BASE, "/blog", crawl, title="Blog", desc="Blog unique desc")
    # Pagination URLs with missing and duplicate meta must be excluded
    for path in ("/blog/page/2", "/blog/page/3", "/blog?page=4", "/a/p/7"):
        seed_crawl_page(db, client_a, BASE, path, crawl, title="", desc="")
    for path in ("/cat/page/2", "/cat/page/3"):
        seed_crawl_page(
            db, client_a, BASE, path, crawl,
            title="Blog", desc="Blog unique desc", dup_title=True, dup_desc=True,
        )
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    checks = {c["key"]: c for c in resp.json()["data"]["seo"]["checks"]}
    for key in ("missing_titles", "duplicate_titles", "missing_descriptions", "duplicate_descriptions"):
        assert checks[key]["total"] == 2
        assert checks[key]["affected"] == 0
        assert checks[key]["urls"] == []
        assert checks[key]["score"] == 100
    assert checks["duplicate_titles"].get("duplicate_groups", []) == []
    assert checks["duplicate_descriptions"].get("duplicate_groups", []) == []


def test_f1_t2_duplicate_grouping_normalizes_case_and_whitespace(client, db, client_a):
    crawl = date.today()
    for path, title in (
        ("/p1", "  Best Sunscreen  "),
        ("/p2", "best sunscreen"),
        ("/p3", "BEST SUNSCREEN "),
    ):
        seed_crawl_page(
            db, client_a, BASE, path, crawl,
            title=title, desc=f"Unique desc {path}", dup_title=True,
        )
    for path, desc in (
        ("/d1", "  Save 20% "),
        ("/d2", "save 20%"),
    ):
        seed_crawl_page(
            db, client_a, BASE, path, crawl,
            title=f"Unique title {path}", desc=desc, dup_desc=True,
        )
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    checks = {c["key"]: c for c in resp.json()["data"]["seo"]["checks"]}

    dt = checks["duplicate_titles"]
    assert dt["affected"] == 3
    assert len(dt["duplicate_groups"]) == 1
    assert dt["duplicate_groups"][0]["count"] == 3
    assert set(dt["duplicate_groups"][0]["urls"]) == {BASE + "/p1", BASE + "/p2", BASE + "/p3"}

    dd = checks["duplicate_descriptions"]
    assert dd["affected"] == 2
    assert len(dd["duplicate_groups"]) == 1
    assert dd["duplicate_groups"][0]["count"] == 2
    assert set(dd["duplicate_groups"][0]["urls"]) == {BASE + "/d1", BASE + "/d2"}


def test_f1_t2_more_than_150_urls_capped_at_urls_kept(client, db, client_a):
    crawl = date.today()
    for i in range(1, 161):
        seed_crawl_page(
            db, client_a, BASE, f"/item-{i:03d}", crawl,
            title="", desc=f"Unique missing title desc {i}",
        )
        seed_crawl_page(
            db, client_a, BASE, f"/dup-{i:03d}", crawl,
            title="Bulk Duplicate", desc=f"Unique dup title desc {i}", dup_title=True,
        )
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    checks = {c["key"]: c for c in resp.json()["data"]["seo"]["checks"]}

    mt = checks["missing_titles"]
    assert mt["affected"] == 160
    assert mt["total"] == 320
    assert len(mt["urls"]) == 150

    dt = checks["duplicate_titles"]
    assert dt["affected"] == 160
    assert dt["total"] == 320
    assert len(dt["urls"]) == 150
    assert len(dt["duplicate_groups"]) == 1
    assert dt["duplicate_groups"][0]["count"] == 160
    assert 1 <= len(dt["duplicate_groups"][0]["urls"]) <= 160


def test_f1_t2_non_indexable_4xx_and_robots_blocked_not_marked_duplicate(client, db, client_a):
    crawl = date.today()
    seed_crawl_page(
        db, client_a, BASE, "/live", crawl,
        status=200, indexable=True, title="Shared", desc="SharedDesc",
        dup_title=False, dup_desc=False,
    )
    seed_crawl_page(
        db, client_a, BASE, "/gone", crawl,
        status=404, indexable=True, title="Shared", desc="SharedDesc",
        dup_title=True, dup_desc=True,
    )
    seed_crawl_page(
        db, client_a, BASE, "/blocked", crawl,
        status=200, blocked_by_robots=True, title="Shared", desc="SharedDesc",
        dup_title=True, dup_desc=True,
    )
    seed_crawl_page(
        db, client_a, BASE, "/noindex", crawl,
        status=200, indexable=False, title="Shared", desc="SharedDesc",
        dup_title=False, dup_desc=False,
    )
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    checks = {c["key"]: c for c in resp.json()["data"]["seo"]["checks"]}

    assert checks["duplicate_titles"]["affected"] == 0
    assert checks["duplicate_titles"].get("duplicate_groups", []) == []
    assert checks["duplicate_descriptions"]["affected"] == 0
    assert checks["duplicate_descriptions"].get("duplicate_groups", []) == []
    assert checks["errors"]["affected"] == 1
    assert checks["errors"]["urls"] == [BASE + "/gone"]
    assert checks["indexation"]["affected"] == 1
    assert checks["indexation"]["urls"] == [BASE + "/noindex"]


def test_f1_t2_whitespace_only_meta_treated_as_missing_not_duplicate(client, db, client_a):
    crawl = date.today()
    seed_crawl_page(db, client_a, BASE, "/ws1", crawl, title="   ", desc="\t\n ")
    seed_crawl_page(db, client_a, BASE, "/ws2", crawl, title=" ", desc="  ")
    seed_crawl_page(db, client_a, BASE, "/ok", crawl, title="Valid", desc="Valid desc")
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    checks = {c["key"]: c for c in resp.json()["data"]["seo"]["checks"]}

    assert checks["missing_titles"]["affected"] == 2
    assert set(checks["missing_titles"]["urls"]) == {BASE + "/ws1", BASE + "/ws2"}
    assert checks["missing_descriptions"]["affected"] == 2
    assert set(checks["missing_descriptions"]["urls"]) == {BASE + "/ws1", BASE + "/ws2"}
    assert checks["duplicate_titles"]["affected"] == 0
    assert checks["duplicate_titles"].get("duplicate_groups", []) == []
    assert checks["duplicate_descriptions"]["affected"] == 0
    assert checks["duplicate_descriptions"].get("duplicate_groups", []) == []


# ── F2: Site Health — By Page, Legacy Snapshots & RBAC Boundaries (6) ────────


def test_f2_t2_legacy_locked_snapshot_synthesizes_by_page_and_site_wide(client, db, client_a):
    seed_snapshot(
        db,
        client_a,
        "2025-06",
        date(2025, 6, 15),
        {
            "month": "2025-06",
            "crawl_date": "2025-06-15",
            "crawl": {"date": "2025-06-15", "pages": 5, "limit": 500, "hit_limit": False},
            "seo": {
                "score": 72,
                "grade": "C",
                "checks": [
                    {"key": "titles", "label": "Titles", "weight": 15, "score": 80, "affected": 1, "total": 5, "urls": [BASE + "/dup"]},
                    {"key": "descriptions", "label": "Descriptions", "weight": 10, "score": 80, "affected": 1, "total": 5, "urls": [BASE + "/nodesc"]},
                    {"key": "errors", "label": "Errors", "weight": 20, "score": 80, "affected": 1, "total": 5, "urls": [BASE + "/dead"]},
                    {"key": "links", "label": "Broken links", "weight": 15, "score": 80, "affected": 1, "total": 5, "urls": [BASE + "/dead"]},
                    {"key": "site_files", "label": "Robots & sitemap", "weight": 10, "score": 60, "affected": 1, "total": 1, "urls": ["no sitemap found"]},
                ],
                "pages": 5,
            },
            "geo": {
                "score": 65,
                "grade": "D",
                "partial": True,
                "answers": None,
                "signals": [
                    {
                        "key": "schema",
                        "label": "Structured data",
                        "weight": 10,
                        "score": 40,
                        "measured": True,
                        "affected": 1,
                        "items": [{"text": "No schema markup on homepage", "url": BASE + "/home"}],
                    },
                    {
                        "key": "entity",
                        "label": "Entity clarity",
                        "weight": 10,
                        "score": 50,
                        "measured": True,
                        "affected": 1,
                        "items": [{"text": "No about page was found in the crawl", "url": None}],
                    },
                ],
            },
            "previous": None,
            "changes": [],
        },
    )
    db.commit()

    resp = client.get("/v2/site-health", params={"month": "2025-06"}, headers=admin_headers(client_a))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["locked"] is True
    assert data["seo"]["score"] == 72
    assert isinstance(data["by_page"], list) and len(data["by_page"]) >= 3
    assert isinstance(data["site_wide"], list) and len(data["site_wide"]) >= 2

    by_page_urls = {p["url"]: p for p in data["by_page"]}
    assert BASE + "/home" in by_page_urls
    for url in (BASE + "/home", BASE + "/dup", BASE + "/nodesc", BASE + "/dead"):
        assert url in by_page_urls
        for iss in by_page_urls[url]["issues"]:
            assert iss["problem"].strip()
            assert iss["fix"].strip()
            assert iss["severity"] in {"high", "medium", "low"}

    sw_keys = {(i["source"], i["key"]) for i in data["site_wide"]}
    assert ("seo", "site_files") in sw_keys
    assert ("geo", "entity") in sw_keys


def test_f2_t2_invalid_month_param_returns_400_and_unknown_month_returns_null_data(client, db, client_a):
    crawl = date.today()
    cur_month = crawl.strftime("%Y-%m")
    seed_crawl_page(db, client_a, BASE, "/", crawl, title="Home", desc="Desc")
    db.commit()

    for bad in ("nope", "2026-13", "2026-00", "26-10"):
        r = client.get("/v2/site-health", params={"month": bad}, headers=admin_headers(client_a))
        assert r.status_code == 400

    unknown_before = client.get("/v2/site-health", params={"month": "2024-01"}, headers=admin_headers(client_a))
    assert unknown_before.status_code == 200
    assert unknown_before.json() == {"month": "2024-01", "months": [], "crawls": [], "compare_to": None, "data": None}

    primed = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert primed.status_code == 200
    assert primed.json()["data"] is not None

    unknown_after = client.get("/v2/site-health", params={"month": "2024-01"}, headers=admin_headers(client_a))
    assert unknown_after.status_code == 200
    after_body = unknown_after.json()
    assert after_body["month"] == "2024-01"
    assert after_body["months"] == [cur_month]
    assert after_body["data"] is None
    assert after_body["compare_to"] is None
    assert len(after_body["crawls"]) == 1


def test_f2_t2_by_page_highest_severity_reflects_max_issue_severity(client, db, client_a):
    crawl = date.today()
    seed_crawl_page(db, client_a, BASE, "/high-only", crawl, status=404, title="", desc="")
    seed_crawl_page(db, client_a, BASE, "/schema-only", crawl, status=200, title="Unique", desc="Unique desc")
    seed_crawl_page(db, client_a, BASE, "/mixed", crawl, status=200, redirects=2, title="Mixed", desc="")
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    by_page = resp.json()["data"]["by_page"]
    rank = {"high": 3, "medium": 2, "low": 1}

    for page in by_page:
        expected_max = max(page["issues"], key=lambda i: rank[i["severity"]])["severity"]
        assert page["highest_severity"] == expected_max

    high_page = next(p for p in by_page if p["url"] == BASE + "/high-only")
    assert high_page["highest_severity"] == "high"


def test_f2_t2_soft_404_and_redirect_chain_surface_in_by_page(client, db, client_a):
    crawl = date.today()
    seed_crawl_page(db, client_a, BASE, "/soft", crawl, status=200, soft_404=True, title="Soft", desc="Soft desc")
    seed_schema(db, client_a, BASE, "/soft", crawl)
    seed_crawl_page(db, client_a, BASE, "/redir", crawl, status=301, redirects=3, title="", desc="")
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    by_page = {p["url"]: p for p in resp.json()["data"]["by_page"]}

    soft_issues = by_page[BASE + "/soft"]["issues"]
    assert any(i["source"] == "seo" and i["key"] == "errors" and i["problem"].strip() and i["fix"].strip() for i in soft_issues)

    redir_issues = by_page[BASE + "/redir"]["issues"]
    assert any(i["source"] == "seo" and i["key"] == "redirects" and i["problem"].strip() and i["fix"].strip() for i in redir_issues)


def test_f2_t2_ai_crawler_blocked_and_unpaired_prompts_routing(client, db, client_a):
    crawl = date.today()
    org_json = '{"@type":"Organization","telephone":"555-0100","address":{"streetAddress":"1 Main"}}'
    for path in ("/", "/about", "/contact"):
        seed_crawl_page(db, client_a, BASE, path, crawl, title=f"Title {path}", desc=f"Desc {path}")
        seed_schema(db, client_a, BASE, path, crawl, kind="Organization", raw_text=org_json)
        seed_schema(db, client_a, BASE, path, crawl, kind="FAQPage")
    seed_crawl_issue(db, client_a, crawl, "ai_crawlers_blocked", normalized_url=None, raw={"agents": ["GPTBot"]})
    seed_llm_run(
        db,
        client_a,
        [
            {
                "query_text": "Unpaired prompt?",
                "platform": "openai",
                "brand_mentioned": False,
                "url_cited": False,
                "full_response": "Short answer.",
            }
        ],
    )
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    data = resp.json()["data"]
    by_page = {p["url"]: p for p in data["by_page"]}

    robots_url = f"https://{client_a.domain}/robots.txt"
    assert robots_url in by_page
    assert any(i["source"] == "geo" and i["key"] == "crawler" for i in by_page[robots_url]["issues"])
    assert all(isinstance(url, str) and url.strip() for url in by_page)

    sw_geo_keys = {i["key"] for i in data["site_wide"] if i["source"] == "geo"}
    assert {"citation", "depth", "attribution", "graph"}.intersection(sw_geo_keys)


def test_f2_t2_client_isolation_and_rbac_enforcement(client, db, client_a, client_b, admin_user):
    crawl = date.today()
    seed_crawl_page(db, client_a, BASE, "/secret-a", crawl, status=404, title="", desc="")
    viewer = make_user(db, email="viewer@clienta.example", role=UserRole.CLIENT_VIEWER, assign_clients=[client_a])
    unassigned_staff = make_user(db, email="other@smamarketing.com", role=UserRole.SMA_TEAM, assign_clients=[client_a])
    db.commit()

    # client_b has zero leakage from client_a
    r_b = client.get("/v2/site-health", headers=admin_headers(client_b))
    assert r_b.status_code == 200
    assert r_b.json() == {"month": None, "months": [], "crawls": [], "compare_to": None, "data": None}

    # CLIENT_VIEWER forbidden
    r_viewer = client.get("/v2/site-health", headers=api_headers(client_a.id, viewer.email))
    assert r_viewer.status_code == 403

    # Unassigned SMA_TEAM forbidden on client_b
    r_unassigned = client.get("/v2/site-health", headers=api_headers(client_b.id, unassigned_staff.email))
    assert r_unassigned.status_code == 403

    # Missing X-OrganicIQ-Client-Id header -> 400
    r_no_hdr = client.get("/v2/site-health", headers=api_headers(None, admin_user.email))
    assert r_no_hdr.status_code == 400


# ── F3: Search Visibility — Unsung Heroes & Watchlist Boundaries (6) ──────────


def test_f3_t2_duplicate_keyword_idempotency_whitespace_and_case_normalization(client, client_a):
    r1 = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "  Mineral   Sunscreen  "},
        headers=admin_headers(client_a),
    )
    assert r1.status_code in (200, 201)
    b1 = r1.json()
    assert b1["created"] is True
    assert b1["keyword_key"] == "mineral sunscreen"

    r2 = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "MINERAL SUNSCREEN"},
        headers=admin_headers(client_a),
    )
    assert r2.status_code in (200, 201)
    b2 = r2.json()
    assert b2["created"] is False
    assert b2["bucket_created"] is False
    assert b2["id"] == b1["id"]
    assert b2["keyword_key"] == "mineral sunscreen"

    wl = client.get("/v2/watchlist", headers=admin_headers(client_a)).json()
    assert wl["keyword_count"] == 1


def test_f3_t2_blank_or_whitespace_keyword_returns_422(client, client_a):
    for bad in ("", "   \t\n  "):
        resp = client.post(
            "/v2/watchlist/keywords",
            json={"keyword": bad},
            headers=admin_headers(client_a),
        )
        assert resp.status_code == 422


def test_f3_t2_invalid_or_cross_client_bucket_id_returns_404(client, db, client_a, client_b):
    other_bucket = seed_bucket(db, client_b, "Client B Bucket")
    db.commit()

    r_missing = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "reef balm", "bucket_id": str(uuid.uuid4())},
        headers=admin_headers(client_a),
    )
    assert r_missing.status_code == 404

    r_cross = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "reef balm", "bucket_id": str(other_bucket.id)},
        headers=admin_headers(client_a),
    )
    assert r_cross.status_code == 404


def test_f3_t2_brand_queries_excluded_from_unsung_heroes(client, db, client_a):
    client_a.client_name = "SunGlow Shop"
    client_a.domain = "sunglowshop.example"
    client_a.brand_aliases = ["sunglow", "sun glow skin"]
    db.flush()

    for q in ("sunglowshop", "sunglow sunscreen", "sun glow skin serum", "vegan mineral balm"):
        seed_gsc(db, client_a, date(2026, 10, 12), q, 800, 5.0, clicks=40)
        seed_gsc(db, client_a, date(2026, 9, 12), q, 100, 12.0, clicks=2)
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    hero_keys = {h["key"] for h in resp.json()["unsung_heroes"]}
    assert "vegan mineral balm" in hero_keys
    assert "sunglowshop" not in hero_keys
    assert "sunglow sunscreen" not in hero_keys
    assert "sun glow skin serum" not in hero_keys


def test_f3_t2_already_on_watchlist_excluded_even_with_case_and_spacing_diff(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Core")
    seed_kw(db, bucket, client_a, "Natural  Sunscreen")
    seed_gsc(db, client_a, date(2026, 10, 10), "  NATURAL   Sunscreen ", 700, 3.0, clicks=55)
    seed_gsc(db, client_a, date(2026, 10, 11), "  NATURAL Sunscreen ", 300, 4.0, clicks=25)
    seed_gsc(db, client_a, date(2026, 9, 10), "  NATURAL   Sunscreen ", 100, 10.0, clicks=5)
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all(h["key"] != "natural sunscreen" for h in data["unsung_heroes"])
    assert len(data["terms"]) == 1
    assert data["terms"][0]["term"] == "Natural  Sunscreen"
    assert data["terms"][0]["google"]["impressions"] >= 300


def test_f3_t2_low_impression_noise_excluded_and_multipage_query_deduplicated(client, db, client_a):
    seed_gsc(db, client_a, date(2026, 10, 10), "tiny query", 3, 1.0, clicks=1)
    seed_gsc(db, client_a, date(2026, 9, 10), "tiny query", 1, 2.0, clicks=0)
    seed_gsc(db, client_a, date(2026, 10, 10), "another tiny", 5, 2.0, clicks=0)
    seed_gsc(db, client_a, date(2026, 10, 10), "broad mineral spf", 400, 5.0, clicks=20, url=BASE + "/p1")
    seed_gsc(db, client_a, date(2026, 10, 10), "broad mineral spf", 100, 9.0, clicks=2, url=BASE + "/p2")
    seed_gsc(db, client_a, date(2026, 9, 10), "broad mineral spf", 100, 10.0, clicks=4, url=BASE + "/p1")
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    heroes = resp.json()["unsung_heroes"]
    hero_keys = [h["key"] for h in heroes]
    assert "tiny query" not in hero_keys
    assert "another tiny" not in hero_keys

    broad_matches = [h for h in heroes if h["key"] == "broad mineral spf"]
    assert len(broad_matches) == 1
    assert broad_matches[0]["impressions"] == 500
    assert broad_matches[0]["page"] == BASE + "/p1"


# ── F4: Search Visibility — Bing Data Boundaries (6) ─────────────────────────


def test_f4_t2_friday_week_start_monday_truncation_alignment_in_bing_series(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Core")
    seed_kw(db, bucket, client_a, "natural sunscreen")
    seed_gsc(db, client_a, date(2026, 10, 7), "natural sunscreen", 100, 4.0)
    seed_bing(db, client_a, date(2026, 10, 9), "natural sunscreen", 100, clicks=6, avg_pos=Decimal("4.0"))
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["weeks"] == ["2026-10-05"]
    assert len(data["bing_series"]) == 1
    assert data["bing_series"][0]["week"] == "2026-10-05"
    assert data["bing_series"][0]["impressions"] == 100
    assert data["bing_series"][0]["clicks"] == 6
    assert data["bing_series"][0]["position"] == 4.0


def test_f4_t2_empty_previous_range_no_zero_division(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Core")
    seed_kw(db, bucket, client_a, "natural sunscreen")
    seed_bing(db, client_a, date(2026, 10, 5), "natural sunscreen", 80, clicks=5, avg_pos=Decimal("5.0"))
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bing_before"]["impressions"] == 0
    assert data["bing_before"]["position"] is None
    assert data["bing_site"]["before"]["impressions"] == 0
    assert data["bing_site"]["before"]["position"] is None
    assert data["terms"][0]["bing"]["position_before"] is None
    assert data["terms"][0]["bing"]["move"] is None
    assert data["bing_winners"] == []
    assert data["bing_losers"] == []


def test_f4_t2_below_10_impressions_position_threshold(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Core")
    seed_kw(db, bucket, client_a, "low imp term")
    seed_kw(db, bucket, client_a, "threshold term")
    seed_bing(db, client_a, date(2026, 10, 5), "low imp term", 9, clicks=0, avg_pos=Decimal("2.0"))
    seed_bing(db, client_a, date(2026, 10, 5), "threshold term", 10, clicks=1, avg_pos=Decimal("2.0"))
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    by_term = {t["term"]: t for t in data["terms"]}
    assert by_term["low imp term"]["bing"]["impressions"] == 9
    assert by_term["low imp term"]["bing"]["position"] is None
    assert by_term["threshold term"]["bing"]["impressions"] == 10
    assert by_term["threshold term"]["bing"]["position"] == 2.0
    assert data["bing_now"]["page_one"] == 1


def test_f4_t2_no_bing_data_returns_has_bing_false(client, db, client_a, client_b):
    bucket = seed_bucket(db, client_a, "Core")
    seed_kw(db, bucket, client_a, "natural sunscreen")
    seed_gsc(db, client_a, date(2026, 10, 10), "natural sunscreen", 200, 5.0)
    # Seed Bing on client_b to confirm isolation
    seed_bing(db, client_b, date(2026, 10, 5), "natural sunscreen", 500, clicks=20, avg_pos=Decimal("2.0"))
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sources"]["has_bing"] is False
    assert data["sources"]["bing_through"] is None
    assert data["sources"]["bing_terms"] == 0
    assert data["sources"]["bing_site_terms"] == 0
    assert data["bing_now"]["impressions"] == 0
    assert data["bing_now"]["position"] is None
    assert data["bing_site"]["now"]["impressions"] == 0
    assert data["bing_winners"] == []
    assert data["bing_losers"] == []


def test_f4_t2_bing_null_avg_position_and_zero_impressions_safe(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Core")
    seed_kw(db, bucket, client_a, "null pos")
    seed_kw(db, bucket, client_a, "zero imp")
    seed_bing(db, client_a, date(2026, 10, 5), "null pos", 30, clicks=0, avg_pos=None)
    seed_bing(db, client_a, date(2026, 10, 5), "zero imp", 0, clicks=0, avg_pos=None)
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    by_term = {t["term"]: t for t in data["terms"]}
    assert by_term["null pos"]["bing"]["impressions"] == 30
    assert by_term["null pos"]["bing"]["position"] is None
    assert by_term["null pos"]["bing"]["move"] is None
    assert by_term["zero imp"]["bing"]["impressions"] == 0
    assert by_term["zero imp"]["bing"]["position"] is None
    assert data["bing_now"]["position"] is None


def test_f4_t2_bing_series_falls_back_to_site_wide_when_watchlist_has_zero_bing_matches(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Core")
    seed_kw(db, bucket, client_a, "google only term")
    seed_gsc(db, client_a, date(2026, 10, 6), "google only term", 120, 4.0)
    seed_bing(db, client_a, date(2026, 10, 5), "other bing query", 90, clicks=4, avg_pos=Decimal("6.0"))
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bing_now"]["impressions"] == 0
    assert data["bing_site"]["now"]["impressions"] == 90
    assert data["sources"]["has_bing"] is True
    oct5 = next(b for b in data["bing_series"] if b["week"] == "2026-10-05")
    assert oct5["impressions"] == 90


# ── F5: Search Visibility — Visibility Check Annotation Boundaries (5) ───────


def test_f5_t2_description_under_3_chars_returns_422(client, client_a):
    for bad in ("", "ab", "  "):
        resp = client.post(
            "/v2/annotations",
            json={"date": "2026-10-15", "description": bad, "type": "visibility_check"},
            headers=admin_headers(client_a),
        )
        assert resp.status_code == 422


def test_f5_t2_invalid_date_and_unknown_type_return_422(client, client_a):
    bad_date = client.post(
        "/v2/annotations",
        json={"date": "2026-13-45", "description": "Bad date check", "type": "visibility_check"},
        headers=admin_headers(client_a),
    )
    assert bad_date.status_code == 422

    bad_type = client.post(
        "/v2/annotations",
        json={"date": "2026-10-15", "description": "Bad type check", "type": "not_a_real_type"},
        headers=admin_headers(client_a),
    )
    assert bad_type.status_code == 422


def test_f5_t2_out_of_range_annotations_excluded_from_search_visibility(client, client_a):
    for d, desc in (
        ("2026-09-30", "Day before start"),
        ("2026-10-15", "Mid range check"),
        ("2026-10-29", "Day after end"),
    ):
        r = client.post(
            "/v2/annotations",
            json={"date": d, "description": desc, "type": "visibility_check"},
            headers=admin_headers(client_a),
        )
        assert r.status_code == 201

    sv = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert sv.status_code == 200
    anns = sv.json()["annotations"]
    assert len(anns) == 1
    assert anns[0]["date"] == "2026-10-15"
    assert anns[0]["description"] == "Mid range check"


def test_f5_t2_old_visibility_check_remains_not_yet_measured_on_read(client, client_a):
    post = client.post(
        "/v2/annotations",
        json={"date": "2025-01-15", "description": "Historical monthly check", "type": "visibility_check"},
        headers=admin_headers(client_a),
    )
    assert post.status_code == 201

    listing = client.get("/v2/annotations", headers=admin_headers(client_a))
    assert listing.status_code == 200
    entry = listing.json()["entries"][0]
    assert entry["result"] == "not_yet_measured"
    assert entry["measure_from"] is None
    assert entry["measure_to"] is None


def test_f5_t2_cross_client_isolation_for_visibility_check_annotations(client, client_a, client_b):
    post = client.post(
        "/v2/annotations",
        json={"date": "2026-10-15", "description": "Client A private check", "type": "visibility_check"},
        headers=admin_headers(client_a),
    )
    assert post.status_code == 201
    ann_id = post.json()["id"]

    sv_b = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_b),
    )
    assert sv_b.status_code == 200
    assert sv_b.json()["annotations"] == []

    list_b = client.get("/v2/annotations", headers=admin_headers(client_b))
    assert list_b.status_code == 200
    assert list_b.json()["entries"] == []

    patch_b = client.patch(
        f"/v2/annotations/{ann_id}",
        json={"notes": "Cross-tenant tamper"},
        headers=admin_headers(client_b),
    )
    assert patch_b.status_code == 404

    del_b = client.delete(f"/v2/annotations/{ann_id}", headers=admin_headers(client_b))
    assert del_b.status_code == 404
