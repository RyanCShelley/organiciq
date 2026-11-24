"""Tier 4 E2E Tests: Realistic multi-step agency & client API workflows (6 scenarios)."""

from __future__ import annotations

from datetime import date, timedelta

from app.models.client import ClientStatus
from app.models.config import OrganicChannel
from app.models.integration import IntegrationProvider
from app.models.user import UserRole
from e2e_phase4.conftest import (
    admin_headers,
    api_headers,
    make_client,
    make_user,
    seed_bucket,
    seed_competitor_kw,
    seed_conversion_def,
    seed_crawl_page,
    seed_ga4_baseline_window,
    seed_ga4_event,
    seed_ga4_traffic,
    seed_gsc_daily,
    seed_gsc_page,
    seed_gsc_query_page,
    seed_indexable_site,
    seed_kw,
    seed_lead_exclusion,
    seed_ser_metric,
    seed_setup_completion_extras,
    seed_watch_target_excluded,
    seed_watermark,
    set_integration,
)


def _step_map(setup_payload: dict) -> dict[str, dict]:
    return {s["key"]: s for s in setup_payload["steps"]}


# ── Scenario 1: New Client Guided Setup Onboarding Lifecycle ──────────────────


def test_t4_scenario_1_new_client_guided_setup_onboarding(client, db, tier, admin_user):
    # Step 1: Create new client via POST /clients
    create_res = client.post(
        "/clients",
        headers=api_headers(email=admin_user.email),
        json={
            "client_name": "Northstar Roofing",
            "domain": "northstarroofing.example",
            "tier_id": str(tier.id),
            "service_mode": "execution",
            "business_model": "lead_gen",
            "service_reporting": {"organiciq": True, "ad_accelerator": False},
        },
    )
    assert create_res.status_code == 201, create_res.text
    created = create_res.json()
    cid = created["id"]
    hdrs = api_headers(client_id=cid, email=admin_user.email)

    # Initial setup checklist: 1/7 done, next="sources", no legacy content_sources/conversion_pages
    s1 = client.get(f"/clients/{cid}/setup", headers=hdrs).json()
    assert s1["done"] == 1
    assert s1["total"] == 7
    assert s1["next"] == "sources"
    keys = [s["key"] for s in s1["steps"]]
    assert "content_sources" not in keys
    assert "conversion_pages" not in keys
    assert _step_map(s1)["competitors"]["optional"] is True

    # Step 2: Connect GA4 & GSC integrations
    from app.models.client import Client

    c_obj = db.get(Client, created["id"])
    assert c_obj is not None
    set_integration(db, c_obj, IntegrationProvider.GA4, "properties/888001")
    set_integration(db, c_obj, IntegrationProvider.GSC, "sc-domain:northstarroofing.example")

    s2 = client.get(f"/clients/{cid}/setup", headers=hdrs).json()
    assert s2["done"] == 2
    assert s2["next"] == "pull"

    # Step 3: Seed 7 complete months of GA4 traffic/events + GSC page pull (before conversion def)
    last_complete = date.today().replace(day=1) - timedelta(days=1)
    cursor_month = last_complete.replace(day=1)
    for idx in range(7):
        total_m = cursor_month.year * 12 + (cursor_month.month - 1) - idx
        y, m = divmod(total_m, 12)
        m_day = date(y, m + 1, 1)
        seed_ga4_traffic(db, c_obj, m_day, 1000, channel=OrganicChannel.ORGANIC_SEARCH, url="/")
        seed_ga4_traffic(db, c_obj, m_day, 350, channel=OrganicChannel.DIRECT_UNATTRIBUTED, url="/")
        seed_ga4_event(db, c_obj, m_day, "request_estimate", 15, channel=OrganicChannel.ORGANIC_SEARCH, url="/")
    seed_watermark(db, c_obj, "ga4", last_complete)
    seed_gsc_page(db, c_obj, last_complete, "/roof-repair", impressions=1400, clicks=55, position=7.8)
    db.commit()

    s3 = client.get(f"/clients/{cid}/setup", headers=hdrs).json()
    assert s3["done"] == 3
    assert s3["next"] == "leads"

    # Step 4: Mark conversion definition via POST /admin/conversion-definitions
    conv_res = client.post(
        "/admin/conversion-definitions",
        headers=hdrs,
        json={
            "event_name": "request_estimate",
            "conversion_name": "Request Estimate",
            "conversion_type": "lead",
            "is_primary": True,
            "active": True,
        },
    )
    assert conv_res.status_code == 201, conv_res.text

    s4 = client.get(f"/clients/{cid}/setup", headers=hdrs).json()
    assert s4["done"] == 4
    assert s4["next"] == "baseline"

    # Step 5: Inspect baseline/series and lock baseline
    series_res = client.get(f"/clients/{cid}/baseline/series", headers=hdrs)
    assert series_res.status_code == 200
    assert series_res.json()["can_lock"] is True

    lock_res = client.post(
        f"/clients/{cid}/baseline/lock",
        headers=hdrs,
        json={"source": "ga4", "months": 24},
    )
    assert lock_res.status_code == 200, lock_res.text

    s5 = client.get(f"/clients/{cid}/setup", headers=hdrs).json()
    assert s5["done"] == 5
    assert s5["next"] == "watchlist"

    # Step 6: Add first watchlist keyword
    kw_res = client.post(
        "/v2/watchlist/keywords",
        headers=hdrs,
        json={"keyword": "roof replacement near me", "bucket_name": "Core Roofing"},
    )
    assert kw_res.status_code == 200

    s6 = client.get(f"/clients/{cid}/setup", headers=hdrs).json()
    assert s6["done"] == 6
    assert s6["next"] == "first_run"

    # Step 7: Complete MonthlyRecord activation deliverable -> 7/7, next is None
    seed_setup_completion_extras(db, c_obj, data_through=last_complete)
    s7 = client.get(f"/clients/{cid}/setup", headers=hdrs).json()
    assert s7["done"] == 7
    assert s7["total"] == 7
    assert s7["next"] is None


# ── Scenario 2: Baseline Clarification & Re-Lock Workflow ─────────────────────


def test_t4_scenario_2_baseline_clarification_and_relock(client, db, tier, admin_user):
    c = make_client(db, tier, "Baseline Lifecycle Co", business_model="lead_gen")
    today = date.today()
    through = seed_ga4_baseline_window(
        db,
        c,
        months=7,
        end_month_day=today.replace(day=min(today.day, 12)),
        sessions_per_month=1500,
        direct_sessions_per_month=500,
        leads_per_month=20,
        include_partial_last_month=True,
    )
    # Seed 30d and 90d FactGscDaily so 3-pillar snapshot has non-null Visibility (never in the future)
    gsc_anchor = min(through, today)
    for offset in (3, 12, 45, 75):
        seed_gsc_daily(db, c, gsc_anchor - timedelta(days=offset), impressions=2500, clicks=120, position=8.5)
    db.commit()

    hdrs = admin_headers(c)

    series_res = client.get(f"/clients/{c.id}/baseline/series", headers=hdrs)
    assert series_res.status_code == 200, series_res.text
    series = series_res.json()
    assert series["status"] == "draft"
    assert len(series["projection"]["checkpoints"]) == 5
    assert series["projection"]["suggested_monthly_lead_goal"] > 0
    assert "monthly_sessions" in series["ranges"]
    assert "lead_rate_pct" in series["ranges"]
    assert any(f["code"] == "partial_month_dropped" and f["level"] == "info" for f in series["flags"])

    # Direct goal update endpoint
    goal_res = client.post(
        f"/clients/{c.id}/baseline/goal",
        headers=hdrs,
        json={"monthly_lead_goal": 48},
    )
    assert goal_res.status_code == 200
    assert goal_res.json()["current"] == 48

    # Lock v1 without target_lead_rate_pct
    v1_res = client.post(
        f"/clients/{c.id}/baseline/lock",
        headers=hdrs,
        json={"source": "ga4", "months": 24, "half_life_months": 3.0},
    )
    assert v1_res.status_code == 200, v1_res.text
    v1 = v1_res.json()
    assert v1["version"]["version"] == 1
    assert v1["goal_set_by_lock"] is True

    # Live 3-pillar snapshot
    pillars_res = client.get(f"/clients/{c.id}/baseline/pillars", headers=hdrs)
    assert pillars_res.status_code == 200
    pillars = pillars_res.json()
    assert pillars["visibility"] is not None
    assert pillars["traffic"] is not None
    assert pillars["leads"] is not None

    # Re-lock v2 with relaunch reason_code & note
    v2_res = client.post(
        f"/clients/{c.id}/baseline/lock",
        headers=hdrs,
        json={
            "source": "ga4",
            "months": 24,
            "reason_code": "relaunch",
            "reason_note": "Full site redesign and URL structure launch.",
            "monthly_lead_goal": 60,
        },
    )
    assert v2_res.status_code == 200, v2_res.text
    assert v2_res.json()["version"]["version"] == 2
    assert v2_res.json()["monthly_lead_goal"] == 60

    versions_res = client.get(f"/clients/{c.id}/baseline/versions", headers=hdrs)
    assert versions_res.status_code == 200
    assert [v["version"] for v in versions_res.json()] == [2, 1]

    v2_detail = client.get(f"/clients/{c.id}/baseline/versions/2", headers=hdrs)
    assert v2_detail.status_code == 200
    assert v2_detail.json()["reason_code"] == "relaunch"
    assert v2_detail.json()["snapshot"]["pillars"] is not None


# ── Scenario 3: Watchlist Editor & GSC Suggestions Lifecycle ──────────────────


def test_t4_scenario_3_watchlist_editor_and_gsc_suggestions(client, db, tier, admin_user):
    c = make_client(db, tier, "Watchlist Workflow Co", brand_aliases=["watchlist workflow", "wwco"])
    set_integration(db, c, IntegrationProvider.GSC, "sc-domain:watchlistworkflow.example")
    recent = date.today() - timedelta(days=2)
    seed_indexable_site(db, c, count=10, snap_date=recent)
    seed_gsc_query_page(db, c, recent, "tankless water heater repair", 640, 8.1, clicks=22, url="/services/item-1")
    seed_gsc_query_page(db, c, recent, "emergency drain cleaning", 510, 9.4, clicks=16, url="/services/item-2")
    seed_gsc_query_page(db, c, recent, "watchlist workflow reviews", 900, 1.3, clicks=120, url="/")
    db.commit()

    hdrs = admin_headers(c)

    # 1. Inspect suggestions: non-brand included, brand excluded
    sugg_1 = client.get("/v2/watchlist/suggestions", headers=hdrs).json()
    assert sugg_1["gsc_connected"] is True
    assert sugg_1["has_gsc_data"] is True
    sugg_keys_1 = {s["key"] for s in sugg_1["suggestions"]}
    assert "tankless water heater repair" in sugg_keys_1
    assert "emergency drain cleaning" in sugg_keys_1
    assert "watchlist workflow reviews" not in sugg_keys_1

    # 2. Add suggestion to new bucket
    add_res = client.post(
        "/v2/watchlist/keywords",
        headers=hdrs,
        json={"keyword": "tankless water heater repair", "bucket_name": "Water Heaters"},
    )
    assert add_res.status_code == 200
    add_body = add_res.json()
    assert add_body["created"] is True
    assert add_body["bucket_created"] is True
    kw_id = add_body["id"]

    # 3. CSV import into another bucket
    csv_res = client.post(
        "/v2/watchlist/import",
        headers=hdrs,
        json={
            "csv_text": "Topic,Keyword,Volume,KD,Intent\nEmergency Services,burst pipe repair,1100,35,commercial\n,sump pump replacement,720,29,transactional\n",
            "dry_run": False,
        },
    )
    assert csv_res.status_code == 200, csv_res.text
    assert csv_res.json()["keywords_created"] == 2

    # 4. Edit keyword metadata & paired AI prompt
    patch_res = client.patch(
        f"/v2/watchlist/keywords/{kw_id}",
        headers=hdrs,
        json={
            "volume": 1850,
            "difficulty": 44,
            "intent": "commercial",
            "paired_ai_prompt": "Who offers reliable tankless water heater repair nearby?",
            "notes": "Priority Q4 service page",
        },
    )
    assert patch_res.status_code == 200, patch_res.text

    # 5. Verify full GET /v2/watchlist state
    wl = client.get("/v2/watchlist", headers=hdrs).json()
    assert wl["keyword_count"] == 3
    by_bucket = {b["name"]: b for b in wl["buckets"]}
    assert set(by_bucket) == {"Water Heaters", "Emergency Services"}
    edited_row = by_bucket["Water Heaters"]["keywords"][0]
    assert edited_row["volume"] == 1850
    assert edited_row["difficulty"] == 44
    assert edited_row["intent"] == "commercial"
    assert edited_row["paired_ai_prompt"] == "Who offers reliable tankless water heater repair nearby?"

    # 6. Delete keyword -> removed from watchlist and reappears in suggestions
    del_res = client.delete(f"/v2/watchlist/keywords/{kw_id}", headers=hdrs)
    assert del_res.status_code == 204

    wl_after = client.get("/v2/watchlist", headers=hdrs).json()
    assert wl_after["keyword_count"] == 2
    sugg_after = client.get("/v2/watchlist/suggestions", headers=hdrs).json()
    assert "tankless water heater repair" in {s["key"] for s in sugg_after["suggestions"]}


# ── Scenario 4: Content Tools (Gaps, Optimizer Ad-Hoc, Sitemap, Feeds 404) ────


def test_t4_scenario_4_content_tools_gaps_optimizer_sitemap(client, db, tier, admin_user, stub_optimizer_llm):
    c = make_client(
        db,
        tier,
        "Content Tools Workflow Co",
        brand_aliases=["content tools workflow", "ctw"],
        competitor_domains=["rivalservice.example"],
    )
    recent = date.today() - timedelta(days=2)
    seed_indexable_site(db, c, count=11, snap_date=recent)
    unranked_url = seed_crawl_page(
        db,
        c,
        f"https://{c.domain}",
        "/services/trenchless-sewer",
        recent,
        title="Trenchless Sewer Repair",
        desc="No-dig sewer line replacement, copper repiping, and residential plumbing pipe repair.",
        sections=[
            {
                "level": 1,
                "heading": "Trenchless Sewer Repair",
                "first_paragraph": (
                    "We replace damaged underground sewer pipes without excavating your yard or driveway."
                ),
            }
        ],
    )
    wl_bucket = seed_bucket(db, c, "Plumbing & Repiping")
    seed_kw(db, wl_bucket, c, "copper pipe repiping")
    seed_kw(db, wl_bucket, c, "sewer plumbing service")

    # Relevant priced gaps
    seed_gsc_query_page(db, c, recent, "hydro jetting sewer line", 450, 12.5, clicks=9, url="/services/item-1")
    seed_ser_metric(db, c, "hydro jetting sewer line", volume=780, difficulty=30)
    seed_competitor_kw(db, c, "rivalservice.example", "copper repiping cost", 4.0, recent, volume=610, difficulty=34)
    seed_ser_metric(db, c, "copper repiping cost", volume=610, difficulty=34)

    # Irrelevant / brand / rival / excluded / low-impression unpriced noise
    # Keep position >= 14.0 & impressions >= 110 so M3's noise/brand/navigational/waiting filters exercise directly
    seed_gsc_query_page(db, c, recent, "ctw login", 300, 15.0, clicks=20, url="/")
    seed_gsc_query_page(db, c, recent, "careers", 280, 16.0, clicks=5, url="/")
    seed_gsc_query_page(db, c, recent, "ac", 260, 17.0, clicks=3, url="/")
    seed_gsc_query_page(db, c, recent, "rivalservice pricing", 320, 15.0, clicks=2, url="/services/item-1")
    seed_gsc_query_page(db, c, recent, "free plumbing sticker", 310, 14.0, clicks=1, url="/services/item-1")
    seed_ser_metric(db, c, "free plumbing sticker", volume=400, difficulty=15)
    seed_watch_target_excluded(db, c, "free plumbing sticker")
    seed_gsc_query_page(db, c, recent, "obscure unpriced phrase", 120, 18.0, clicks=0, url="/services/item-2")
    db.commit()

    hdrs = admin_headers(c)

    # 1. Content gaps filtering
    gaps_res = client.get("/v2/content/gaps", headers=hdrs)
    assert gaps_res.status_code == 200, gaps_res.text
    gap_terms = {g["term"] for g in gaps_res.json()["gaps"]}
    assert "hydro jetting sewer line" in gap_terms
    assert "copper repiping cost" in gap_terms
    for noise in ("ctw login", "careers", "ac", "rivalservice pricing", "free plumbing sticker", "obscure unpriced phrase"):
        assert noise not in gap_terms

    # 2. Content Optimizer ad-hoc keyword on unranked URL
    opt_res = client.post(
        "/v2/optimizer/draft",
        headers=hdrs,
        json={
            "url": unranked_url,
            "kind": "opening",
            "depth": "quick",
            "keyword": "trenchless sewer line replacement",
        },
    )
    assert opt_res.status_code == 202, opt_res.text
    page_res = client.get("/v2/optimizer/page", headers=hdrs, params={"url": unranked_url}).json()
    draft = page_res["drafts"]["opening"]
    assert draft["status"] == "done"
    assert draft["keyword"] == "trenchless sewer line replacement"
    assert len(draft["options"]) >= 1

    # 3. Update sitemap_url & verify /v2/feeds is 404
    new_sitemap = f"https://{c.domain}/sitemap-v2.xml"
    patch_res = client.patch(f"/clients/{c.id}", headers=hdrs, json={"sitemap_url": new_sitemap})
    assert patch_res.status_code == 200
    assert patch_res.json()["sitemap_url"] == new_sitemap
    assert client.get("/v2/feeds", headers=hdrs).status_code == 404


# ── Scenario 5: Agency All-Clients Overview & Multi-Tenant RBAC ───────────────


def test_t4_scenario_5_agency_all_clients_overview_and_rbac(client, db, tier):
    today = date.today()
    recent = today - timedelta(days=2)
    prior = today - timedelta(days=38)

    alpha = make_client(db, tier, "Agency Alpha", business_model="lead_gen", monthly_lead_goal=25)
    beta = make_client(db, tier, "Agency Beta", business_model="lead_gen", monthly_lead_goal=40)
    gamma = make_client(db, tier, "Agency Gamma Null", status=ClientStatus.ONBOARDING, service_mode="consulting")

    # Alpha: 2000 impr / 100 clicks; 900 organic / 1200 total; 14 valid leads (5 excluded on /test-form)
    seed_conversion_def(db, alpha, "generate_lead", conversion_type="lead", active=True, is_primary=True)
    seed_conversion_def(db, alpha, "page_engagement", conversion_type="engagement", active=True, is_primary=False)
    seed_lead_exclusion(db, alpha, url_pattern=f"https://{alpha.domain}/test-form*", reason="QA form")
    seed_gsc_daily(db, alpha, recent, impressions=2000, clicks=100, position=9.0)
    seed_gsc_daily(db, alpha, prior, impressions=1600, clicks=80, position=10.0)
    seed_ga4_traffic(db, alpha, recent, 900, channel=OrganicChannel.ORGANIC_SEARCH, url="/")
    seed_ga4_traffic(db, alpha, recent, 300, channel=OrganicChannel.DIRECT_UNATTRIBUTED, url="/")
    seed_ga4_traffic(db, alpha, prior, 750, channel=OrganicChannel.ORGANIC_SEARCH, url="/")
    seed_ga4_event(db, alpha, recent, "generate_lead", 14, url="/services")
    seed_ga4_event(db, alpha, recent, "generate_lead", 5, url="/test-form")
    seed_ga4_event(db, alpha, recent, "page_engagement", 50, url="/services")

    # Beta: 5000 impr / 250 clicks; 2100 organic / 2600 total; 30 leads
    seed_conversion_def(db, beta, "book_consult", conversion_type="lead", active=True, is_primary=True)
    seed_gsc_daily(db, beta, recent, impressions=5000, clicks=250, position=5.5)
    seed_ga4_traffic(db, beta, recent, 2100, channel=OrganicChannel.ORGANIC_SEARCH, url="/")
    seed_ga4_traffic(db, beta, recent, 500, channel=OrganicChannel.DIRECT_UNATTRIBUTED, url="/")
    seed_ga4_event(db, beta, recent, "book_consult", 30, url="/book")
    db.commit()

    admin = make_user(db, email="agency-admin@smamarketing.com", role=UserRole.SMA_ADMIN)
    team = make_user(db, email="agency-team@smamarketing.com", role=UserRole.SMA_TEAM, assign_clients=[alpha])
    viewer = make_user(db, email="viewer@agency-alpha.example", role=UserRole.CLIENT_VIEWER, assign_clients=[alpha])

    # Admin sees all 3 clients with exact aggregated metrics
    ov_admin = client.get("/v2/clients/overview", headers=api_headers(email=admin.email))
    assert ov_admin.status_code == 200
    by_id = {item["id"]: item for item in ov_admin.json()["clients"]}
    assert set(by_id) == {str(alpha.id), str(beta.id), str(gamma.id)}

    a_row = by_id[str(alpha.id)]
    assert a_row["impressions"] == 2000
    assert a_row["clicks"] == 100
    assert a_row["avg_position"] == 9.0
    assert a_row["organic_sessions"] == 900
    assert a_row["total_sessions"] == 1200
    assert a_row["leads"] == 14

    b_row = by_id[str(beta.id)]
    assert b_row["impressions"] == 5000
    assert b_row["organic_sessions"] == 2100
    assert b_row["leads"] == 30

    g_row = by_id[str(gamma.id)]
    assert g_row["impressions"] is None
    assert g_row["organic_sessions"] is None
    assert g_row["leads"] is None

    # SMA_TEAM scoped strictly to alpha
    ov_team = client.get("/v2/clients/overview", headers=api_headers(email=team.email))
    assert ov_team.status_code == 200
    assert [item["id"] for item in ov_team.json()["clients"]] == [str(alpha.id)]

    # CLIENT_VIEWER receives 403 across all staff endpoints
    viewer_hdrs = api_headers(alpha.id, viewer.email)
    for path in (
        "/v2/clients/overview",
        f"/clients/{alpha.id}/setup",
        "/v2/watchlist",
        "/v2/watchlist/suggestions",
        "/v2/content/gaps",
        "/v2/optimizer",
    ):
        resp = client.get(path, headers=viewer_hdrs)
        assert resp.status_code == 403, f"Expected 403 for CLIENT_VIEWER on {path}, got {resp.status_code}"


# ── Scenario 6: Consulting Client Lifecycle ───────────────────────────────────


def test_t4_scenario_6_consulting_client_lifecycle(client, db, admin_user):
    create_res = client.post(
        "/clients",
        headers=api_headers(email=admin_user.email),
        json={
            "client_name": "Summit Advisory Partners",
            "domain": "summitadvisory.example",
            "service_mode": "consulting",
            "business_model": "lead_gen",
        },
    )
    assert create_res.status_code == 201, create_res.text
    created = create_res.json()
    cid = created["id"]
    assert created["service_mode"] == "consulting"
    assert created["plan_label"] == "Consulting"

    hdrs = api_headers(cid, admin_user.email)
    setup_1 = client.get(f"/clients/{cid}/setup", headers=hdrs).json()
    assert setup_1["service_mode"] == "consulting"
    step_keys = [s["key"] for s in setup_1["steps"]]
    assert "consulting_profile" in step_keys
    assert "consulting_deliverable" in step_keys
    assert "first_run" not in step_keys
    assert _step_map(setup_1)["account"]["done"] is True

    # Connect sources, seed GA4/GSC, lock baseline, add watchlist, complete consulting deliverables
    from app.models.client import Client

    c_obj = db.get(Client, cid)
    assert c_obj is not None
    set_integration(db, c_obj, IntegrationProvider.GA4, "properties/999001")
    set_integration(db, c_obj, IntegrationProvider.GSC, "sc-domain:summitadvisory.example")
    through = seed_ga4_baseline_window(db, c_obj, months=7, leads_per_month=11)
    seed_gsc_page(db, c_obj, through, "/advisory", impressions=800, clicks=30, position=7.5)
    db.commit()

    lock_res = client.post(f"/clients/{cid}/baseline/lock", headers=hdrs, json={"source": "ga4", "months": 24})
    assert lock_res.status_code == 200, lock_res.text

    kw_res = client.post(
        "/v2/watchlist/keywords",
        headers=hdrs,
        json={"keyword": "fractional cfo services", "bucket_name": "Advisory"},
    )
    assert kw_res.status_code == 200

    seed_setup_completion_extras(db, c_obj, data_through=through)
    setup_final = client.get(f"/clients/{cid}/setup", headers=hdrs).json()
    assert setup_final["done"] == setup_final["total"]
    assert setup_final["next"] is None

    # Overview handles consulting client cleanly
    ov = client.get("/v2/clients/overview", headers=hdrs).json()
    row = next(item for item in ov["clients"] if item["id"] == cid)
    assert row["service_mode"] == "consulting"
    assert row["plan_label"] == "Consulting"
