"""Tier 1 E2E Tests: Happy-path functional coverage across Features F1–F5 (28 tests)."""

from __future__ import annotations

import uuid
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
    seed_llm_run,
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


# ── F1: Site Health — Missing vs Duplicate Meta & Shared-Text Grouping (6) ───


def test_f1_t1_missing_and_duplicate_titles_reported_separately(client, db, client_a):
    crawl = date.today()
    for path, title, dup in (
        ("/a", "Unique Title A", False),
        ("/b", "Unique Title B", False),
        ("/m1", "", False),
        ("/m2", None, False),
        ("/d1", "Shared Title", True),
        ("/d2", "Shared Title", True),
    ):
        seed_crawl_page(
            db, client_a, BASE, path, crawl,
            title=title, desc=f"Unique desc for {path}", dup_title=dup,
        )
        seed_schema(db, client_a, BASE, path, crawl)
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data is not None
    checks = {c["key"]: c for c in data["seo"]["checks"]}

    assert "titles" not in checks
    missing = checks["missing_titles"]
    dup = checks["duplicate_titles"]
    assert missing["affected"] == 2
    assert missing["total"] == 6
    assert set(missing["urls"]) == {BASE + "/m1", BASE + "/m2"}

    assert dup["affected"] == 2
    assert dup["total"] == 6
    assert set(dup["urls"]) == {BASE + "/d1", BASE + "/d2"}
    assert set(missing["urls"]).isdisjoint(set(dup["urls"]))


def test_f1_t1_missing_and_duplicate_descriptions_reported_separately(client, db, client_a):
    crawl = date.today()
    for path, desc, dup in (
        ("/a", "Unique desc A", False),
        ("/b", "Unique desc B", False),
        ("/md1", "", False),
        ("/md2", None, False),
        ("/dd1", "Shared Description", True),
        ("/dd2", "Shared Description", True),
    ):
        seed_crawl_page(
            db, client_a, BASE, path, crawl,
            title=f"Unique title for {path}", desc=desc, dup_desc=dup,
        )
        seed_schema(db, client_a, BASE, path, crawl)
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    checks = {c["key"]: c for c in resp.json()["data"]["seo"]["checks"]}

    assert "descriptions" not in checks
    missing = checks["missing_descriptions"]
    dup = checks["duplicate_descriptions"]
    assert missing["affected"] == 2
    assert missing["total"] == 6
    assert set(missing["urls"]) == {BASE + "/md1", BASE + "/md2"}

    assert dup["affected"] == 2
    assert dup["total"] == 6
    assert set(dup["urls"]) == {BASE + "/dd1", BASE + "/dd2"}
    assert set(missing["urls"]).isdisjoint(set(dup["urls"]))


def test_f1_t1_duplicate_titles_grouped_by_shared_text(client, db, client_a):
    crawl = date.today()
    for path in ("/g1a", "/g1b", "/g1c"):
        seed_crawl_page(
            db, client_a, BASE, path, crawl,
            title="Widget Guide", desc=f"Desc {path}", dup_title=True,
        )
    for path in ("/g2a", "/g2b"):
        seed_crawl_page(
            db, client_a, BASE, path, crawl,
            title="Pricing FAQ", desc=f"Desc {path}", dup_title=True,
        )
    seed_crawl_page(db, client_a, BASE, "/uniq", crawl, title="Home", desc="Unique home desc")
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    checks = {c["key"]: c for c in resp.json()["data"]["seo"]["checks"]}
    dup = checks["duplicate_titles"]
    groups = dup["duplicate_groups"]
    assert len(groups) == 2

    by_text = {norm_key(g["text"]): g for g in groups}
    assert set(by_text) == {"widget guide", "pricing faq"}
    assert by_text["widget guide"]["count"] == 3
    assert set(by_text["widget guide"]["urls"]) == {BASE + "/g1a", BASE + "/g1b", BASE + "/g1c"}
    assert by_text["pricing faq"]["count"] == 2
    assert set(by_text["pricing faq"]["urls"]) == {BASE + "/g2a", BASE + "/g2b"}
    assert all(BASE + "/uniq" not in g["urls"] for g in groups)


def test_f1_t1_duplicate_descriptions_grouped_by_shared_text(client, db, client_a):
    crawl = date.today()
    for path in ("/d1a", "/d1b"):
        seed_crawl_page(
            db, client_a, BASE, path, crawl,
            title=f"Title {path}", desc="Shop organic SPF", dup_desc=True,
        )
    for path in ("/d2a", "/d2b"):
        seed_crawl_page(
            db, client_a, BASE, path, crawl,
            title=f"Title {path}", desc="Free shipping today", dup_desc=True,
        )
    seed_crawl_page(db, client_a, BASE, "/uniq", crawl, title="Home", desc="Totally unique")
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    checks = {c["key"]: c for c in resp.json()["data"]["seo"]["checks"]}
    dup = checks["duplicate_descriptions"]
    groups = dup["duplicate_groups"]
    assert len(groups) == 2
    assert dup["affected"] == 4

    by_text = {norm_key(g["text"]): g for g in groups}
    assert set(by_text) == {"shop organic spf", "free shipping today"}
    assert by_text["shop organic spf"]["count"] == 2
    assert set(by_text["shop organic spf"]["urls"]) == {BASE + "/d1a", BASE + "/d1b"}
    assert by_text["free shipping today"]["count"] == 2
    assert set(by_text["free shipping today"]["urls"]) == {BASE + "/d2a", BASE + "/d2b"}
    for g in groups:
        assert len(g["urls"]) == g["count"]


def test_f1_t1_seo_check_weights_sum_to_100_and_match_contract(client, db, client_a):
    crawl = date.today()
    for path, title, desc in (
        ("/", "Home Page", "Home page description"),
        ("/about", "About Us", "About page description"),
    ):
        seed_crawl_page(db, client_a, BASE, path, crawl, title=title, desc=desc)
        seed_schema(db, client_a, BASE, path, crawl, kind="Organization")
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    data = resp.json()["data"]
    checks = data["seo"]["checks"]

    expected_weights = {
        "missing_titles": 8,
        "duplicate_titles": 7,
        "missing_descriptions": 5,
        "duplicate_descriptions": 5,
        "indexation": 15,
        "errors": 20,
        "redirects": 5,
        "links": 15,
        "schema": 10,
        "site_files": 10,
    }
    actual_weights = {c["key"]: c["weight"] for c in checks}
    assert actual_weights == expected_weights
    assert sum(actual_weights.values()) == 100
    assert data["weights"]["seo"] == expected_weights
    assert all(c["score"] == 100 for c in checks)
    assert data["seo"]["score"] == 100
    assert data["seo"]["grade"] == "A+"


def test_f1_t1_previous_month_comparison_and_changes_preserved(client, db, client_a):
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
            "locked": True,
            "crawl_date": prev_date.isoformat(),
            "crawl": {"date": prev_date.isoformat(), "pages": 4, "limit": 500, "hit_limit": False},
            "seo": {
                "score": 80,
                "grade": "B",
                "checks": [
                    {
                        "key": "missing_titles",
                        "label": "Missing titles",
                        "weight": 8,
                        "score": 100,
                        "affected": 0,
                        "total": 4,
                        "urls": [],
                    },
                    {
                        "key": "duplicate_titles",
                        "label": "Duplicate titles",
                        "weight": 7,
                        "score": 50,
                        "affected": 2,
                        "total": 4,
                        "urls": [BASE + "/d1", BASE + "/d2"],
                    },
                    {
                        "key": "errors",
                        "label": "Broken pages",
                        "weight": 20,
                        "score": 75,
                        "affected": 1,
                        "total": 4,
                        "urls": [BASE + "/err"],
                    },
                ],
                "pages": 4,
            },
            "geo": {"score": 75, "grade": "B-", "signals": [], "partial": True, "answers": None},
            "previous": None,
            "changes": [],
        },
    )

    seed_crawl_page(db, client_a, BASE, "/d1", today, title="Now Unique 1", desc="Desc 1", dup_title=False)
    seed_crawl_page(db, client_a, BASE, "/d2", today, title="Now Unique 2", desc="Desc 2", dup_title=False)
    seed_crawl_page(db, client_a, BASE, "/err", today, status=200, title="Fixed Page", desc="Desc err")
    seed_crawl_page(db, client_a, BASE, "/m1", today, title="", desc="Desc m1")
    db.commit()

    resp = client.get("/v2/site-health", params={"month": cur_month}, headers=admin_headers(client_a))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["previous"]["month"] == prev_month
    assert data["previous"]["seo"] == 80
    assert data["previous"]["geo"] == 75
    assert isinstance(data["seo"]["score"], int)
    assert isinstance(data["seo"]["grade"], str) and data["seo"]["grade"]
    assert isinstance(data["geo"]["score"], int)
    assert isinstance(data["geo"]["grade"], str) and data["geo"]["grade"]

    changes = {c["key"]: c for c in data["changes"]}
    assert changes["duplicate_titles"]["fixed_count"] == 2
    assert set(changes["duplicate_titles"]["fixed"]) == {BASE + "/d1", BASE + "/d2"}
    assert changes["errors"]["fixed_count"] == 1
    assert changes["errors"]["fixed"] == [BASE + "/err"]
    assert changes["missing_titles"]["new_count"] == 1
    assert changes["missing_titles"]["new"] == [BASE + "/m1"]


# ── F2: Site Health — By Page Merge, Prescribed Fixes & Routing (6) ──────────


def test_f2_t1_seo_and_geo_issues_merged_per_url_in_by_page(client, db, client_a):
    crawl = date.today()
    # Homepage has missing title, missing desc, missing schema (SEO + GEO schema/faq/entity)
    seed_crawl_page(db, client_a, BASE, "/", crawl, title="", desc="")
    seed_crawl_page(db, client_a, BASE, "/about", crawl, title="About", desc="About page")
    seed_schema(db, client_a, BASE, "/about", crawl, kind="Article")
    seed_crawl_page(db, client_a, BASE, "/contact", crawl, title="Contact", desc="Contact page")
    seed_schema(db, client_a, BASE, "/contact", crawl, kind="Article")
    seed_gsc(db, client_a, crawl, "main keyword", 500, 5.0, clicks=25, url=BASE + "/")
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    by_page = resp.json()["data"]["by_page"]
    urls = [p["url"] for p in by_page]
    assert len(urls) == len(set(urls)), "Each URL must appear at most once in by_page"

    home = next(p for p in by_page if p["url"] == BASE + "/")
    issues = home["issues"]
    sources = {i["source"] for i in issues}
    assert sources == {"seo", "geo"}
    assert home["seo_count"] == sum(1 for i in issues if i["source"] == "seo")
    assert home["geo_count"] == sum(1 for i in issues if i["source"] == "geo")
    assert home["issue_count"] == len(issues) == home["seo_count"] + home["geo_count"]
    assert home["seo_count"] >= 2 and home["geo_count"] >= 2


def test_f2_t1_every_by_page_and_site_wide_issue_has_deterministic_problem_fix_severity(client, db, client_a):
    crawl = date.today()
    seed_crawl_page(db, client_a, BASE, "/", crawl, title="", desc="Home desc")
    seed_crawl_page(db, client_a, BASE, "/dup1", crawl, title="Dup", desc="DupDesc", dup_title=True, dup_desc=True)
    seed_crawl_page(db, client_a, BASE, "/dup2", crawl, title="Dup", desc="DupDesc", dup_title=True, dup_desc=True)
    seed_crawl_page(db, client_a, BASE, "/noindex", crawl, title="NoIdx", desc="NoIdx desc", indexable=False)
    seed_crawl_page(db, client_a, BASE, "/broken", crawl, status=404, title="", desc="")
    seed_crawl_page(db, client_a, BASE, "/redir", crawl, status=301, redirects=2, title="Redir", desc="Redir")
    seed_internal_link(db, client_a, crawl, BASE + "/", BASE + "/broken")
    seed_crawl_issue(db, client_a, crawl, "sitemap_missing")
    seed_crawl_issue(db, client_a, crawl, "ai_crawlers_blocked", raw={"agents": ["GPTBot"]})
    seed_gsc(db, client_a, crawl, "faq query", 400, 4.0, clicks=10, url=BASE + "/")
    bucket = seed_bucket(db, client_a, "Core")
    seed_kw(db, bucket, client_a, "faq query", paired_ai_prompt="What is organic skincare?")
    seed_llm_run(
        db,
        client_a,
        [
            {
                "query_text": "What is organic skincare?",
                "platform": "openai",
                "brand_mentioned": False,
                "url_cited": False,
                "full_response": "Short generic answer.",
            }
        ],
    )
    db.commit()

    first = client.get("/v2/site-health", headers=admin_headers(client_a))
    second = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert first.status_code == 200 and second.status_code == 200
    d1, d2 = first.json()["data"], second.json()["data"]
    assert d1["by_page"] and d1["site_wide"]
    assert d1["by_page"] == d2["by_page"]
    assert d1["site_wide"] == d2["site_wide"]

    all_issues = [iss for page in d1["by_page"] for iss in page["issues"]] + d1["site_wide"]
    for iss in all_issues:
        assert iss["source"] in {"seo", "geo"}
        assert isinstance(iss["key"], str) and iss["key"].strip()
        assert isinstance(iss["label"], str) and iss["label"].strip()
        assert iss["severity"] in {"high", "medium", "low"}
        assert "subject" in iss
        assert isinstance(iss["problem"], str) and iss["problem"].strip()
        assert isinstance(iss["fix"], str) and iss["fix"].strip()


def test_f2_t1_broken_internal_links_attributed_to_from_url_not_to_url(client, db, client_a):
    crawl = date.today()
    org_json = '{"@type":"Organization","telephone":"555-0100","address":{"streetAddress":"1 Main St"}}'
    for path, title, desc in (
        ("/source-page", "Source Page", "Source description"),
        ("/about", "About", "About description"),
        ("/contact", "Contact", "Contact description"),
    ):
        seed_crawl_page(db, client_a, BASE, path, crawl, title=title, desc=desc)
        seed_schema(db, client_a, BASE, path, crawl, kind="Organization", raw_text=org_json)
        seed_schema(db, client_a, BASE, path, crawl, kind="FAQPage")
    seed_crawl_page(db, client_a, BASE, "/dead-target", crawl, status=404, title="", desc="")
    seed_internal_link(db, client_a, crawl, BASE + "/source-page", BASE + "/dead-target")
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    by_page = {p["url"]: p for p in resp.json()["data"]["by_page"]}

    assert BASE + "/source-page" in by_page
    source_keys = [i["key"] for i in by_page[BASE + "/source-page"]["issues"]]
    assert "links" in source_keys

    assert BASE + "/dead-target" in by_page
    dead_keys = [i["key"] for i in by_page[BASE + "/dead-target"]["issues"]]
    assert "errors" in dead_keys
    assert "links" not in dead_keys


def test_f2_t1_site_files_and_null_url_geo_items_routed_to_site_wide(client, db, client_a):
    crawl = date.today()
    # Deliberately omit /about and /contact to trigger url=None entity issues
    seed_crawl_page(db, client_a, BASE, "/", crawl, title="Home", desc="Home desc")
    seed_crawl_page(db, client_a, BASE, "/products", crawl, title="Products", desc="Products desc")
    seed_crawl_issue(db, client_a, crawl, "sitemap_missing")
    seed_crawl_issue(db, client_a, crawl, "no_robots")
    seed_llm_run(
        db,
        client_a,
        [
            {
                "query_text": "Best sunscreen brand?",
                "platform": "openai",
                "brand_mentioned": False,
                "url_cited": False,
                "full_response": "Generic answer with no brand.",
            }
        ],
    )
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    data = resp.json()["data"]
    site_wide = data["site_wide"]
    by_page = data["by_page"]

    assert all(isinstance(p["url"], str) and p["url"].strip() for p in by_page)
    sw_keys = {(i["source"], i["key"]) for i in site_wide}
    assert ("seo", "site_files") in sw_keys
    assert ("geo", "entity") in sw_keys
    assert ("geo", "graph") in sw_keys


def test_f2_t1_clean_pages_omitted_from_by_page(client, db, client_a):
    crawl = date.today()
    org_json = '{"@type":"Organization","telephone":"555-0100","address":{"streetAddress":"1 Main St"}}'
    for path, title, desc in (
        ("/clean", "Clean Page", "Clean description"),
        ("/about", "About Page", "About description"),
        ("/contact", "Contact Page", "Contact description"),
    ):
        seed_crawl_page(db, client_a, BASE, path, crawl, title=title, desc=desc)
        seed_schema(db, client_a, BASE, path, crawl, kind="Organization", raw_text=org_json)
        seed_schema(db, client_a, BASE, path, crawl, kind="FAQPage")
    seed_crawl_page(db, client_a, BASE, "/broken", crawl, status=404, title="", desc="")
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    urls_in_by_page = {p["url"] for p in resp.json()["data"]["by_page"]}
    assert BASE + "/clean" not in urls_in_by_page
    assert BASE + "/broken" in urls_in_by_page


def test_f2_t1_duplicate_meta_issues_in_by_page_include_shared_text_and_peers(client, db, client_a):
    crawl = date.today()
    for path in ("/d1", "/d2"):
        seed_crawl_page(
            db, client_a, BASE, path, crawl,
            title="Duplicate Title", desc=f"Unique desc {path}", dup_title=True,
        )
        seed_schema(db, client_a, BASE, path, crawl)
    seed_crawl_page(db, client_a, BASE, "/clean", crawl, title="Unique Title", desc="Unique desc clean")
    seed_schema(db, client_a, BASE, "/clean", crawl)
    db.commit()

    resp = client.get("/v2/site-health", headers=admin_headers(client_a))
    assert resp.status_code == 200
    by_page = {p["url"]: p for p in resp.json()["data"]["by_page"]}

    for path in ("/d1", "/d2"):
        url = BASE + path
        assert url in by_page
        dup_issues = [i for i in by_page[url]["issues"] if i["source"] == "seo" and i["key"] == "duplicate_titles"]
        assert len(dup_issues) == 1
        iss = dup_issues[0]
        assert iss["problem"].strip() and iss["fix"].strip()
        combined = f"{iss.get('subject') or ''} {iss['problem']}".lower()
        assert "duplicate title" in combined


# ── F3: Search Visibility — GSC "Unsung Heroes" & Watchlist Add (6) ──────────


def test_f3_t1_unsung_heroes_surfaces_untracked_qualifying_queries_only(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Sunscreen")
    seed_kw(db, bucket, client_a, "natural sunscreen")

    # Current range: Oct 1-28, Previous range: Sep 3-30
    seed_gsc(db, client_a, date(2026, 10, 10), "natural sunscreen", 400, 5.0, clicks=20)
    seed_gsc(db, client_a, date(2026, 10, 12), "reef safe lip balm", 600, 8.0, clicks=30, url=BASE + "/lip-balm")
    seed_gsc(db, client_a, date(2026, 9, 12), "reef safe lip balm", 150, 14.0, clicks=5, url=BASE + "/lip-balm")
    seed_gsc(db, client_a, date(2026, 10, 14), "zinc stick for kids", 450, 6.0, clicks=22, url=BASE + "/zinc-stick")
    seed_gsc(db, client_a, date(2026, 9, 14), "zinc stick for kids", 100, 11.0, clicks=4, url=BASE + "/zinc-stick")
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert [t["term"] for t in data["terms"]] == ["natural sunscreen"]
    heroes = {h["key"]: h for h in data["unsung_heroes"]}
    assert "natural sunscreen" not in heroes
    assert "reef safe lip balm" in heroes
    assert "zinc stick for kids" in heroes

    expected_keys = {
        "query", "key", "page", "impressions", "impressions_before",
        "impressions_change_pct", "clicks", "position", "position_before",
        "move", "ctr", "signals", "relevance_note",
    }
    lip = heroes["reef safe lip balm"]
    assert expected_keys.issubset(lip.keys())
    assert lip["impressions"] == 600
    assert lip["impressions_before"] == 150
    assert lip["clicks"] == 30
    assert lip["position"] == 8.0
    assert lip["position_before"] == 14.0
    assert lip["move"] == 6.0
    assert lip["page"] == BASE + "/lip-balm"
    assert isinstance(lip["signals"], list) and len(lip["signals"]) >= 1
    assert isinstance(lip["relevance_note"], str) and lip["relevance_note"].strip()


def test_f3_t1_add_to_watchlist_auto_creates_general_bucket_when_none_exist(client, db, client_a):
    resp = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "mineral body lotion", "notes": "From unsung heroes"},
        headers=admin_headers(client_a),
    )
    assert resp.status_code in (200, 201)
    body = resp.json()
    assert body["keyword"] == "mineral body lotion"
    assert body["keyword_key"] == "mineral body lotion"
    assert body["bucket_name"] == "General"
    assert body["created"] is True
    assert body["bucket_created"] is True
    assert uuid.UUID(body["id"])
    assert uuid.UUID(body["bucket_id"])

    wl = client.get("/v2/watchlist", headers=admin_headers(client_a))
    assert wl.status_code == 200
    wl_data = wl.json()
    assert wl_data["keyword_count"] == 1
    assert len(wl_data["buckets"]) == 1
    assert wl_data["buckets"][0]["name"] == "General"
    assert wl_data["buckets"][0]["keywords"][0]["notes"] == "From unsung heroes"


def test_f3_t1_add_to_watchlist_explicit_bucket_id(client, db, client_a):
    seed_bucket(db, client_a, "Alpha", sort_order=0)
    beta = seed_bucket(db, client_a, "Beta", sort_order=1)
    db.commit()

    resp = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "after sun gel", "bucket_id": str(beta.id)},
        headers=admin_headers(client_a),
    )
    assert resp.status_code in (200, 201)
    body = resp.json()
    assert body["bucket_id"] == str(beta.id)
    assert body["bucket_name"] == "Beta"
    assert body["created"] is True
    assert body["bucket_created"] is False

    sv = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat(), "bucket": str(beta.id)},
        headers=admin_headers(client_a),
    )
    assert sv.status_code == 200
    assert [t["term"] for t in sv.json()["terms"]] == ["after sun gel"]


def test_f3_t1_add_to_watchlist_bucket_name_creates_then_reuses_normalized(client, db, client_a):
    r1 = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "spf lip oil", "bucket_name": "Lip Care"},
        headers=admin_headers(client_a),
    )
    assert r1.status_code in (200, 201)
    b1 = r1.json()
    assert b1["bucket_name"] == "Lip Care"
    assert b1["bucket_created"] is True
    assert b1["created"] is True

    r2 = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "tinted lip balm", "bucket_name": "  lip   care  "},
        headers=admin_headers(client_a),
    )
    assert r2.status_code in (200, 201)
    b2 = r2.json()
    assert b2["bucket_id"] == b1["bucket_id"]
    assert b2["bucket_created"] is False
    assert b2["created"] is True

    wl = client.get("/v2/watchlist", headers=admin_headers(client_a)).json()
    assert len(wl["buckets"]) == 1
    assert wl["keyword_count"] == 2


def test_f3_t1_add_to_watchlist_defaults_to_first_existing_bucket_when_omitted(client, db, client_a):
    priority = seed_bucket(db, client_a, "Priority One", sort_order=0)
    seed_bucket(db, client_a, "Secondary", sort_order=1)
    db.commit()

    resp = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "organic facial mist"},
        headers=admin_headers(client_a),
    )
    assert resp.status_code in (200, 201)
    body = resp.json()
    assert body["bucket_id"] == str(priority.id)
    assert body["bucket_name"] == "Priority One"
    assert body["bucket_created"] is False
    assert body["created"] is True

    wl = client.get("/v2/watchlist", headers=admin_headers(client_a)).json()
    assert len(wl["buckets"]) == 2


def test_f3_t1_promoting_unsung_hero_moves_it_to_terms_and_excludes_from_unsung_heroes(client, db, client_a):
    core = seed_bucket(db, client_a, "Core")
    seed_kw(db, core, client_a, "mineral spf")
    seed_gsc(db, client_a, date(2026, 10, 10), "mineral spf", 200, 5.0, clicks=10)
    seed_gsc(db, client_a, date(2026, 10, 12), "zinc oxide lotion", 700, 7.0, clicks=40)
    seed_gsc(db, client_a, date(2026, 9, 12), "zinc oxide lotion", 200, 12.0, clicks=8)
    db.commit()

    before = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    ).json()
    assert "zinc oxide lotion" in {h["key"] for h in before["unsung_heroes"]}
    assert "zinc oxide lotion" not in {t["term"].lower() for t in before["terms"]}

    add = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "zinc oxide lotion", "bucket_id": str(core.id)},
        headers=admin_headers(client_a),
    )
    assert add.status_code in (200, 201)

    after = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    ).json()
    assert "zinc oxide lotion" not in {h["key"] for h in after["unsung_heroes"]}
    terms_by_key = {t["term"].lower(): t for t in after["terms"]}
    assert "zinc oxide lotion" in terms_by_key
    promoted = terms_by_key["zinc oxide lotion"]
    assert promoted["google"]["impressions"] == 700
    assert promoted["google"]["position"] == 7.0
    assert promoted["move"] == 5.0


# ── F4: Search Visibility — Elevated Bing KPIs, Trends & Movers (5) ──────────


def test_f4_t1_bing_kpis_now_before_and_sources_metadata(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Sunscreen")
    seed_kw(db, bucket, client_a, "natural sunscreen")
    seed_kw(db, bucket, client_a, "mineral spf")

    seed_bing(db, client_a, date(2026, 10, 5), "natural sunscreen", 60, clicks=5, avg_pos=Decimal("4.0"))
    seed_bing(db, client_a, date(2026, 10, 12), "mineral spf", 40, clicks=2, avg_pos=Decimal("12.0"))
    seed_bing(db, client_a, date(2026, 9, 7), "natural sunscreen", 50, clicks=2, avg_pos=Decimal("8.0"))
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["sources"]["has_bing"] is True
    assert data["sources"]["bing_through"] == "2026-10-12"
    assert data["sources"]["bing_terms"] == 2

    assert data["bing_now"]["showing"] == 2
    assert data["bing_now"]["page_one"] == 1
    assert data["bing_now"]["impressions"] == 100
    assert data["bing_now"]["clicks"] == 7
    assert data["bing_now"]["position"] == 7.2

    assert data["bing_before"]["showing"] == 1
    assert data["bing_before"]["impressions"] == 50
    assert data["bing_before"]["position"] == 8.0


def test_f4_t1_bing_site_totals_include_untracked_bing_queries(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Sunscreen")
    seed_kw(db, bucket, client_a, "natural sunscreen")

    seed_bing(db, client_a, date(2026, 10, 5), "natural sunscreen", 50, clicks=3, avg_pos=Decimal("6.0"))
    seed_bing(db, client_a, date(2026, 10, 5), "sunblock stick", 150, clicks=10, avg_pos=Decimal("4.0"))
    seed_bing(db, client_a, date(2026, 9, 7), "sunblock stick", 100, clicks=4, avg_pos=Decimal("8.0"))
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["bing_now"]["impressions"] == 50
    assert data["bing_site"]["now"]["impressions"] == 200
    assert data["bing_site"]["now"]["clicks"] == 13
    assert data["bing_site"]["now"]["showing"] == 2
    assert data["bing_site"]["before"]["impressions"] == 100
    assert data["sources"]["bing_site_terms"] == 2
    assert data["sources"]["bing_terms"] == 1


def test_f4_t1_bing_series_aligned_to_weekly_buckets(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Sunscreen")
    seed_kw(db, bucket, client_a, "natural sunscreen")
    seed_gsc(db, client_a, date(2026, 10, 6), "natural sunscreen", 100, 4.0, clicks=5)
    seed_gsc(db, client_a, date(2026, 10, 13), "natural sunscreen", 100, 4.0, clicks=5)
    seed_bing(db, client_a, date(2026, 10, 5), "natural sunscreen", 30, clicks=2, avg_pos=Decimal("5.0"))
    seed_bing(db, client_a, date(2026, 10, 12), "natural sunscreen", 70, clicks=5, avg_pos=Decimal("7.0"))
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["weeks"] == ["2026-10-05", "2026-10-12"]
    assert [b["week"] for b in data["bing_series"]] == data["weeks"]
    assert data["bing_series"][0]["impressions"] == 30
    assert data["bing_series"][0]["clicks"] == 2
    assert data["bing_series"][0]["position"] == 5.0
    assert data["bing_series"][1]["impressions"] == 70
    assert data["bing_series"][1]["clicks"] == 5
    assert data["bing_series"][1]["position"] == 7.0


def test_f4_t1_bing_winners_losers_and_per_term_position_before_and_move(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Sunscreen")
    seed_kw(db, bucket, client_a, "natural sunscreen")
    seed_kw(db, bucket, client_a, "mineral spf")

    seed_bing(db, client_a, date(2026, 9, 7), "natural sunscreen", 50, clicks=2, avg_pos=Decimal("15.0"))
    seed_bing(db, client_a, date(2026, 10, 5), "natural sunscreen", 60, clicks=4, avg_pos=Decimal("4.0"))
    seed_bing(db, client_a, date(2026, 9, 7), "mineral spf", 50, clicks=4, avg_pos=Decimal("3.0"))
    seed_bing(db, client_a, date(2026, 10, 5), "mineral spf", 40, clicks=1, avg_pos=Decimal("14.0"))
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert _mover_names(data["bing_winners"]) == ["natural sunscreen"]
    assert _mover_names(data["bing_losers"]) == ["mineral spf"]

    by_term = {t["term"]: t for t in data["terms"]}
    assert by_term["natural sunscreen"]["bing"]["position_before"] == 15.0
    assert by_term["natural sunscreen"]["bing"]["move"] == 11.0
    assert by_term["mineral spf"]["bing"]["position_before"] == 3.0
    assert by_term["mineral spf"]["bing"]["move"] == -11.0


def test_f4_t1_bing_visible_when_watchlist_is_empty(client, db, client_a):
    seed_bing(db, client_a, date(2026, 10, 5), "untracked spf", 120, clicks=8, avg_pos=Decimal("5.0"))
    seed_bing(db, client_a, date(2026, 9, 7), "untracked spf", 80, clicks=4, avg_pos=Decimal("9.0"))
    db.commit()

    resp = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["terms"] == []
    assert data["terms_total"] == 0
    assert data["sources"]["has_bing"] is True
    assert data["sources"]["bing_site_terms"] == 1
    assert data["sources"]["bing_through"] == "2026-10-05"
    assert data["bing_site"]["now"]["impressions"] == 120
    assert data["bing_site"]["before"]["impressions"] == 80
    assert "2026-10-05" in data["weeks"]
    assert [b["week"] for b in data["bing_series"]] == data["weeks"]


# ── F5: Search Visibility — Visibility Check Annotations & Markers (5) ───────


def test_f5_t1_post_visibility_check_creates_unmeasured_annotation(client, db, client_a):
    post = client.post(
        "/v2/annotations",
        json={
            "date": "2026-10-15",
            "description": "October monthly visibility check",
            "type": "visibility_check",
        },
        headers=admin_headers(client_a),
    )
    assert post.status_code == 201
    created_id = post.json()["id"]
    assert uuid.UUID(created_id)

    listing = client.get("/v2/annotations", headers=admin_headers(client_a))
    assert listing.status_code == 200
    body = listing.json()
    assert "visibility_check" in body["types"]
    assert any(t["key"] == "visibility_check" for t in body["manual_types"])

    entry = next(e for e in body["entries"] if e["id"] == created_id)
    assert entry["type"] == "visibility_check"
    assert entry["type_label"] == "Visibility check"
    assert entry["description"] == "October monthly visibility check"
    assert entry["measure_from"] is None
    assert entry["measure_to"] is None
    assert entry["result"] == "not_yet_measured"
    assert entry["how"] == "Added by hand"


def test_f5_t1_search_visibility_returns_in_range_annotations_for_chart_markers(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Core")
    seed_kw(db, bucket, client_a, "natural sunscreen")
    seed_gsc(db, client_a, date(2026, 10, 10), "natural sunscreen", 200, 5.0)
    db.commit()

    r1 = client.post(
        "/v2/annotations",
        json={"date": "2026-10-14", "description": "Mid-month check", "type": "visibility_check"},
        headers=admin_headers(client_a),
    )
    r2 = client.post(
        "/v2/annotations",
        json={"date": "2026-10-20", "description": "Added new landing page", "type": "manual_note"},
        headers=admin_headers(client_a),
    )
    assert r1.status_code == 201 and r2.status_code == 201

    sv = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert sv.status_code == 200
    anns = sv.json()["annotations"]
    assert len(anns) == 2
    expected_keys = {"id", "date", "type", "type_label", "description", "notes"}
    for ann in anns:
        assert expected_keys.issubset(ann.keys())
    vc = next(a for a in anns if a["type"] == "visibility_check")
    assert vc["date"] == "2026-10-14"
    assert vc["type_label"] == "Visibility check"


def test_f5_t1_patch_visibility_check_notes_reflected_in_search_visibility(client, db, client_a):
    post = client.post(
        "/v2/annotations",
        json={"date": "2026-10-10", "description": "Weekly check", "type": "visibility_check"},
        headers=admin_headers(client_a),
    )
    assert post.status_code == 201
    ann_id = post.json()["id"]

    patch = client.patch(
        f"/v2/annotations/{ann_id}",
        json={"notes": "Top 10 gained 2 keywords on Bing"},
        headers=admin_headers(client_a),
    )
    assert patch.status_code == 200
    assert patch.json()["notes"] == "Top 10 gained 2 keywords on Bing"

    sv = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert sv.status_code == 200
    match = next(a for a in sv.json()["annotations"] if a["id"] == ann_id)
    assert match["notes"] == "Top 10 gained 2 keywords on Bing"


def test_f5_t1_delete_visibility_check_removes_chart_marker(client, db, client_a):
    post = client.post(
        "/v2/annotations",
        json={"date": "2026-10-12", "description": "Temporary check", "type": "visibility_check"},
        headers=admin_headers(client_a),
    )
    assert post.status_code == 201
    ann_id = post.json()["id"]

    delete = client.delete(f"/v2/annotations/{ann_id}", headers=admin_headers(client_a))
    assert delete.status_code == 200
    assert delete.json() == {"ok": True}

    sv = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    ).json()
    listing = client.get("/v2/annotations", headers=admin_headers(client_a)).json()
    assert all(a["id"] != ann_id for a in sv["annotations"])
    assert all(e["id"] != ann_id for e in listing["entries"])


def test_f5_t1_annotations_on_exact_start_and_end_range_boundaries_included(client, db, client_a):
    r_start = client.post(
        "/v2/annotations",
        json={"date": START.isoformat(), "description": "Start boundary check", "type": "visibility_check"},
        headers=admin_headers(client_a),
    )
    r_end = client.post(
        "/v2/annotations",
        json={"date": END.isoformat(), "description": "End boundary check", "type": "visibility_check"},
        headers=admin_headers(client_a),
    )
    assert r_start.status_code == 201 and r_end.status_code == 201

    sv = client.get(
        "/v2/search-visibility",
        params={"from": START.isoformat(), "to": END.isoformat()},
        headers=admin_headers(client_a),
    )
    assert sv.status_code == 200
    dates = {a["date"] for a in sv.json()["annotations"]}
    assert dates == {START.isoformat(), END.isoformat()}
