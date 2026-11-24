"""Tier 1 E2E Tests: Happy-path functional coverage across Phase 4 Features F1–F11 (51 tests)."""

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
    norm_key,
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
    set_integration,
)


def _step_map(setup_payload: dict) -> dict[str, dict]:
    return {step["key"]: step for step in setup_payload["steps"]}


# ── Group 1: F1/F2 Guided Setup Checklist (6 tests) ──────────────────────────


def test_f1_t1_setup_execution_steps_streamlined_and_pruned(client, db, tier):
    c = make_client(db, tier, "Setup Streamlined Plumbing")
    resp = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c))
    assert resp.status_code == 200
    body = resp.json()

    assert body["service_mode"] == "execution"
    steps = _step_map(body)
    expected_required = {"account", "sources", "pull", "leads", "baseline", "watchlist", "first_run"}
    assert expected_required.issubset(steps.keys())
    assert "content_sources" not in steps
    assert "conversion_pages" not in steps

    assert steps["competitors"]["optional"] is True
    assert body["total"] == len(expected_required)
    assert body["done"] == 1
    assert steps["account"]["done"] is True
    assert body["next"] == "sources"


def test_f1_t1_setup_step_progression_updates_done_next_and_blocked_by(client, db, tier):
    c = make_client(db, tier, "Setup Progression Co")
    today = date.today()

    # Initial: account done, pull/leads/baseline/first_run blocked
    r0 = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c)).json()
    s0 = _step_map(r0)
    assert r0["done"] == 1
    assert r0["next"] == "sources"
    assert s0["pull"]["blocked_by"]
    assert s0["leads"]["blocked_by"]
    assert s0["baseline"]["blocked_by"]
    assert s0["first_run"]["blocked_by"]

    # Step 2: connect GA4 + GSC -> sources done, next=pull
    set_integration(db, c, IntegrationProvider.GA4, "properties/111222")
    set_integration(db, c, IntegrationProvider.GSC, "sc-domain:setupprog.example")
    r1 = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c)).json()
    s1 = _step_map(r1)
    assert r1["done"] == 2
    assert s1["sources"]["done"] is True
    assert s1["pull"]["blocked_by"] is None
    assert r1["next"] == "pull"

    # Step 3: seed GA4 + GSC data -> pull done, next=leads
    seed_ga4_baseline_window(db, c, months=7, leads_per_month=10)
    # Remove auto-seeded conversion def to isolate pull -> leads transition
    from app.models.config import ConversionDefinition

    db.query(ConversionDefinition).filter(ConversionDefinition.client_id == c.id).delete()
    seed_gsc_page(db, c, today - timedelta(days=2), "/services/pipe-repair", 150, 12, position=6.5)
    db.commit()

    r2 = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c)).json()
    s2 = _step_map(r2)
    assert r2["done"] == 3
    assert s2["pull"]["done"] is True
    assert s2["leads"]["blocked_by"] is None
    assert s2["first_run"]["blocked_by"] is None
    assert r2["next"] == "leads"

    # Step 4: seed lead conversion def -> leads done, next=baseline
    seed_conversion_def(db, c, event_name="generate_lead")
    r3 = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c)).json()
    s3 = _step_map(r3)
    assert r3["done"] == 4
    assert s3["leads"]["done"] is True
    assert s3["baseline"]["blocked_by"] is None
    assert r3["next"] == "baseline"

    # Step 5: lock baseline -> baseline done, next=watchlist
    lock_resp = client.post(
        f"/clients/{c.id}/baseline/lock",
        json={"source": "ga4"},
        headers=admin_headers(c),
    )
    assert lock_resp.status_code == 200
    r4 = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c)).json()
    s4 = _step_map(r4)
    assert r4["done"] == 5
    assert s4["baseline"]["done"] is True
    assert r4["next"] == "watchlist"

    # Step 6: add watchlist keyword -> watchlist done, next=first_run
    bucket = seed_bucket(db, c, "Core Services")
    seed_kw(db, bucket, c, "emergency plumber")
    db.commit()
    r5 = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c)).json()
    assert r5["done"] == 6
    assert r5["next"] == "first_run"


def test_f1_t1_setup_links_use_web_v2_routes_without_legacy_paths(client, db, tier):
    c = make_client(db, tier, "Setup Links Co")
    resp = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c))
    assert resp.status_code == 200
    steps = _step_map(resp.json())

    assert steps["account"]["link"] == "settings"
    assert steps["sources"]["link"] == "settings/connections"
    assert steps["pull"]["link"] == "settings/connections"
    assert steps["leads"]["link"] == "settings/conversions"
    assert steps["baseline"]["link"] == "settings/baseline"
    assert steps["watchlist"]["link"] == "watchlist"
    assert steps["first_run"]["link"] == "engine"

    for step in steps.values():
        assert "keyword-map" not in step["link"]
        assert "decision-engine" not in step["link"]


def test_f1_t1_setup_consulting_mode_adapts_checklist_steps(client, db, tier):
    c = make_client(db, tier, "Setup Consulting Client", service_mode="consulting")
    resp = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c))
    assert resp.status_code == 200
    body = resp.json()
    steps = _step_map(body)

    assert body["service_mode"] == "consulting"
    assert "consulting_profile" in steps
    assert "consulting_deliverable" in steps
    assert "first_run" not in steps
    assert body["total"] == 8
    assert steps["consulting_profile"]["link"] == "consulting"
    assert steps["consulting_deliverable"]["link"] == "consulting/recommendations"


def test_f2_t1_post_clients_creates_execution_and_consulting_reflected_in_setup(
    client, db, admin_user, tier
):
    exec_resp = client.post(
        "/clients",
        json={
            "client_name": "Oakridge HVAC",
            "domain": "oakridgehvac.example",
            "tier_id": str(tier.id),
            "service_mode": "execution",
        },
        headers=api_headers(email="admin@smamarketing.com"),
    )
    assert exec_resp.status_code == 201
    exec_id = exec_resp.json()["id"]
    exec_setup = client.get(
        f"/clients/{exec_id}/setup",
        headers=api_headers(email="admin@smamarketing.com"),
    )
    assert exec_setup.status_code == 200
    assert exec_setup.json()["service_mode"] == "execution"
    assert exec_setup.json()["total"] == 7

    consult_resp = client.post(
        "/clients",
        json={
            "client_name": "Pinecrest Advisory",
            "domain": "pinecrestadvisory.example",
            "service_mode": "consulting",
        },
        headers=api_headers(email="admin@smamarketing.com"),
    )
    assert consult_resp.status_code == 201
    consult_data = consult_resp.json()
    assert consult_data["service_mode"] == "consulting"
    assert consult_data["tier_id"] is not None

    consult_setup = client.get(
        f"/clients/{consult_data['id']}/setup",
        headers=api_headers(email="admin@smamarketing.com"),
    )
    assert consult_setup.status_code == 200
    assert consult_setup.json()["service_mode"] == "consulting"
    assert consult_setup.json()["total"] == 8


def test_f1_t1_setup_full_completion_yields_done_eq_total_and_next_none_ignoring_optional(
    client, db, tier
):
    c = make_client(db, tier, "Setup Complete Plumbing", competitor_domains=[])
    set_integration(db, c, IntegrationProvider.GA4, "properties/777888")
    set_integration(db, c, IntegrationProvider.GSC, "sc-domain:setupcomplete.example")
    seed_ga4_baseline_window(db, c, months=7, leads_per_month=12)
    seed_gsc_page(
        db, c, date.today() - timedelta(days=2), "/services/drain-cleaning", 300, 20, position=4.5
    )
    bucket = seed_bucket(db, c, "Main")
    seed_kw(db, bucket, c, "drain cleaning service")
    seed_setup_completion_extras(db, c)
    db.commit()

    lock_resp = client.post(
        f"/clients/{c.id}/baseline/lock",
        json={"source": "ga4"},
        headers=admin_headers(c),
    )
    assert lock_resp.status_code == 200

    setup = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c)).json()
    steps = _step_map(setup)
    assert steps["competitors"]["optional"] is True
    assert steps["competitors"]["done"] is False
    assert setup["done"] == setup["total"] == 7
    assert setup["next"] is None


# ── Group 2: F3 Baseline & Projections (6 tests) ─────────────────────────────


def test_f3_t1_baseline_series_returns_draft_ranges_window_series_and_flags(client, db, tier):
    c = make_client(db, tier, "Baseline Series Plumbing")
    seed_ga4_baseline_window(
        db,
        c,
        months=7,
        sessions_per_month=1500,
        leads_per_month=25,
        include_partial_last_month=True,
    )

    resp = client.get(f"/clients/{c.id}/baseline/series", headers=admin_headers(c))
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "draft"
    assert data["baseline"]["monthly_sessions"] > 0
    assert data["baseline"]["monthly_leads"] > 0
    assert data["baseline"]["lead_rate_pct"] > 0
    assert set(data["ranges"]) >= {"monthly_sessions", "lead_rate_pct", "monthly_leads"}
    assert "regime_start" in data["window"]
    assert data["window"]["months"] == 7
    assert len(data["series"]) == 7
    assert any(flag["code"] == "partial_month_dropped" for flag in data["flags"])


def test_f3_t1_baseline_series_returns_12_month_projection_checkpoints_and_suggested_goal(
    client, db, tier
):
    c = make_client(db, tier, "Baseline Projection Co")
    seed_ga4_baseline_window(db, c, months=7, sessions_per_month=2000, leads_per_month=30)

    resp = client.get(f"/clients/{c.id}/baseline/series", headers=admin_headers(c))
    assert resp.status_code == 200
    data = resp.json()

    for key in ("projection", "projection_point"):
        proj = data[key]
        labels = [cp["label"] for cp in proj["checkpoints"]]
        assert labels == ["Today", "3 months", "6 months", "9 months", "12 months"]
        assert proj["goal_horizon_months"] == 12
        assert isinstance(proj["suggested_monthly_lead_goal"], int)
        assert proj["suggested_monthly_lead_goal"] >= round(data["baseline"]["monthly_leads"])


def test_f3_t1_baseline_goal_endpoint_updates_goal_pre_and_post_lock(client, db, tier):
    c = make_client(db, tier, "Baseline Goal Update Co")
    seed_ga4_baseline_window(db, c, months=7, sessions_per_month=1200, leads_per_month=15)

    pre = client.post(
        f"/clients/{c.id}/baseline/goal",
        json={"monthly_lead_goal": 28},
        headers=admin_headers(c),
    )
    assert pre.status_code == 200
    assert pre.json()["current"] == 28

    lock_resp = client.post(
        f"/clients/{c.id}/baseline/lock",
        json={"source": "ga4"},
        headers=admin_headers(c),
    )
    assert lock_resp.status_code == 200

    post = client.post(
        f"/clients/{c.id}/baseline/goal",
        json={"monthly_lead_goal": 42},
        headers=admin_headers(c),
    )
    assert post.status_code == 200
    assert post.json()["current"] == 42

    client_row = client.get(f"/clients/{c.id}", headers=admin_headers(c)).json()
    assert client_row["monthly_lead_goal"] == 42


def test_f3_t1_baseline_lock_v1_clean_without_target_rate_updates_setup(client, db, tier):
    c = make_client(db, tier, "Baseline Lock Clean Co")
    set_integration(db, c, IntegrationProvider.GA4, "properties/444555")
    set_integration(db, c, IntegrationProvider.GSC, "sc-domain:baselinelock.example")
    seed_ga4_baseline_window(db, c, months=7, sessions_per_month=1800, leads_per_month=24)

    lock_resp = client.post(
        f"/clients/{c.id}/baseline/lock",
        json={"source": "ga4"},
        headers=admin_headers(c),
    )
    assert lock_resp.status_code == 200
    locked = lock_resp.json()
    assert locked["version"]["version"] == 1
    assert locked["version"]["reason_code"] == "initial"
    assert locked["goal_set_by_lock"] is True
    assert locked["monthly_lead_goal"] == locked["suggested_monthly_lead_goal"]

    setup_steps = _step_map(client.get(f"/clients/{c.id}/setup", headers=admin_headers(c)).json())
    assert setup_steps["baseline"]["done"] is True


def test_f3_t1_baseline_versions_and_pillars_return_3_pillar_snapshot(client, db, tier):
    c = make_client(db, tier, "Baseline Pillars Co")
    through = seed_ga4_baseline_window(db, c, months=7, sessions_per_month=1000, leads_per_month=12)
    seed_gsc_daily(db, c, through - timedelta(days=5), impressions=900, clicks=45, position=8.2)
    db.commit()

    lock_resp = client.post(
        f"/clients/{c.id}/baseline/lock",
        json={"source": "ga4"},
        headers=admin_headers(c),
    )
    assert lock_resp.status_code == 200

    versions_resp = client.get(f"/clients/{c.id}/baseline/versions", headers=admin_headers(c))
    assert versions_resp.status_code == 200
    versions = versions_resp.json()
    assert len(versions) == 1
    assert versions[0]["version"] == 1
    assert versions[0]["has_pillars"] is True

    v1_resp = client.get(f"/clients/{c.id}/baseline/versions/1", headers=admin_headers(c))
    assert v1_resp.status_code == 200
    pillars_v1 = v1_resp.json()["snapshot"]["pillars"]
    assert set(pillars_v1) >= {"window", "visibility", "traffic", "leads"}

    live_pillars = client.get(f"/clients/{c.id}/baseline/pillars", headers=admin_headers(c))
    assert live_pillars.status_code == 200
    pillars_live = live_pillars.json()
    assert set(pillars_live) >= {"window", "visibility", "traffic", "leads"}
    assert pillars_live["visibility"]["gsc"]["impressions"]["recent_30d"] >= 0
    assert pillars_live["traffic"]["total_sessions"]["total_90d"] >= 0
    assert pillars_live["leads"]["total"]["total_90d"] >= 0


def test_f3_t1_baseline_relock_v2_with_reason_code_and_note_increments_version(client, db, tier):
    c = make_client(db, tier, "Baseline Relock Co")
    seed_ga4_baseline_window(db, c, months=7, sessions_per_month=1400, leads_per_month=18)

    v1 = client.post(
        f"/clients/{c.id}/baseline/lock",
        json={"source": "ga4"},
        headers=admin_headers(c),
    )
    assert v1.status_code == 200
    assert v1.json()["version"]["version"] == 1

    v2 = client.post(
        f"/clients/{c.id}/baseline/lock",
        json={
            "source": "ga4",
            "reason_code": "tracking_change",
            "reason_note": "Deduplicated thank-you page conversion firing across mobile forms.",
            "monthly_lead_goal": 36,
        },
        headers=admin_headers(c),
    )
    assert v2.status_code == 200
    data = v2.json()
    assert data["version"]["version"] == 2
    assert data["version"]["reason_code"] == "tracking_change"
    assert data["monthly_lead_goal"] == 36

    versions = client.get(f"/clients/{c.id}/baseline/versions", headers=admin_headers(c)).json()
    assert [v["version"] for v in versions] == [2, 1]


# ── Group 3: F4 Watchlist Keyword & Bucket CRUD (6 tests) ────────────────────


def test_f4_t1_watchlist_bucket_create_rename_reorder_and_delete(client, db, client_a):
    headers = admin_headers(client_a)
    b1 = client.post("/v2/watchlist/buckets", json={"name": "Emergency Repair"}, headers=headers)
    assert b1.status_code == 201
    b1_id = b1.json()["id"]

    b2 = client.post("/v2/watchlist/buckets", json={"name": "Installations"}, headers=headers)
    assert b2.status_code == 201
    b2_id = b2.json()["id"]

    patch_b1 = client.patch(
        f"/v2/watchlist/buckets/{b1_id}",
        json={"name": "Urgent Plumbing", "sort_order": 5},
        headers=headers,
    )
    assert patch_b1.status_code == 200
    assert patch_b1.json()["name"] == "Urgent Plumbing"
    assert patch_b1.json()["sort_order"] == 5

    patch_b2 = client.patch(
        f"/v2/watchlist/buckets/{b2_id}",
        json={"sort_order": 1},
        headers=headers,
    )
    assert patch_b2.status_code == 200

    wl = client.get("/v2/watchlist", headers=headers).json()
    assert [b["name"] for b in wl["buckets"]] == ["Installations", "Urgent Plumbing"]

    del_b2 = client.delete(f"/v2/watchlist/buckets/{b2_id}", headers=headers)
    assert del_b2.status_code == 200
    assert del_b2.json()["deleted"] is True

    wl_after = client.get("/v2/watchlist", headers=headers).json()
    assert [b["id"] for b in wl_after["buckets"]] == [b1_id]


def test_f4_t1_watchlist_keyword_minimal_quick_add_and_extended_fields(client, db, client_a):
    headers = admin_headers(client_a)
    bucket = client.post("/v2/watchlist/buckets", json={"name": "Core Services"}, headers=headers).json()

    quick = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "water heater repair", "bucket_id": bucket["id"]},
        headers=headers,
    )
    assert quick.status_code == 200
    q_data = quick.json()
    assert q_data["created"] is True
    assert q_data["bucket_id"] == bucket["id"]

    extended = client.post(
        "/v2/watchlist/keywords",
        json={
            "keyword": "tankless water heater installation",
            "bucket_name": "Installations",
            "volume": 1200,
            "difficulty": 34,
            "intent": "commercial",
            "paired_ai_prompt": "Best tankless water heater installers near me",
            "notes": "Priority Q2 service page",
        },
        headers=headers,
    )
    assert extended.status_code == 200
    e_data = extended.json()
    assert e_data["created"] is True
    assert e_data["bucket_created"] is True
    assert e_data["bucket_name"] == "Installations"

    wl = client.get("/v2/watchlist", headers=headers).json()
    assert wl["keyword_count"] == 2
    by_kw = {k["keyword"]: k for b in wl["buckets"] for k in b["keywords"]}
    assert by_kw["water heater repair"]["volume"] is None
    assert by_kw["tankless water heater installation"]["volume"] == 1200
    assert by_kw["tankless water heater installation"]["difficulty"] == 34
    assert by_kw["tankless water heater installation"]["intent"] == "commercial"
    assert (
        by_kw["tankless water heater installation"]["paired_ai_prompt"]
        == "Best tankless water heater installers near me"
    )
    assert by_kw["tankless water heater installation"]["notes"] == "Priority Q2 service page"


def test_f4_t1_watchlist_keyword_patch_updates_all_editable_fields(client, db, client_a):
    headers = admin_headers(client_a)
    b1 = client.post("/v2/watchlist/buckets", json={"name": "Drain Services"}, headers=headers).json()
    b2 = client.post("/v2/watchlist/buckets", json={"name": "Sewer Services"}, headers=headers).json()
    kw = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "drain cleaning", "bucket_id": b1["id"]},
        headers=headers,
    ).json()

    patched = client.patch(
        f"/v2/watchlist/keywords/{kw['id']}",
        json={
            "keyword": "hydro jetting drain cleaning",
            "bucket_id": b2["id"],
            "volume": 880,
            "difficulty": 27,
            "intent": "transactional",
            "paired_ai_prompt": "Who offers hydro jetting drain cleaning?",
            "notes": "Updated after client intake call",
        },
        headers=headers,
    )
    assert patched.status_code == 200
    p = patched.json()
    assert p["keyword"] == "hydro jetting drain cleaning"
    assert p["bucket_id"] == b2["id"]
    assert p["bucket_name"] == "Sewer Services"
    assert p["volume"] == 880
    assert p["difficulty"] == 27
    assert p["intent"] == "transactional"
    assert p["paired_ai_prompt"] == "Who offers hydro jetting drain cleaning?"
    assert p["notes"] == "Updated after client intake call"


def test_f4_t1_watchlist_keyword_delete_updates_get_watchlist(client, db, client_a):
    headers = admin_headers(client_a)
    k1 = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "sewer line inspection", "bucket_name": "Diagnostics"},
        headers=headers,
    ).json()
    k2 = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "camera pipe inspection", "bucket_name": "Diagnostics"},
        headers=headers,
    ).json()

    del_resp = client.delete(f"/v2/watchlist/keywords/{k1['id']}", headers=headers)
    assert del_resp.status_code == 204

    wl = client.get("/v2/watchlist", headers=headers).json()
    assert wl["keyword_count"] == 1
    remaining_ids = [k["id"] for b in wl["buckets"] for k in b["keywords"]]
    assert remaining_ids == [k2["id"]]


def test_f4_t1_watchlist_csv_import_creates_buckets_and_keywords(client, db, client_a):
    headers = admin_headers(client_a)
    csv_text = (
        "Topic,Keyword,Volume,KD,Intent,Paired AI Prompt,Notes\n"
        "Water Heaters,water heater replacement,1900,41,transactional,Best water heater replacement company,Top revenue\n"
        ",anode rod replacement,480,18,informational,,Maintenance article\n"
        "Drains,clogged main sewer line,1300,35,commercial,,Urgent service\n"
    )
    resp = client.post(
        "/v2/watchlist/import",
        json={"csv_text": csv_text, "dry_run": False},
        headers=headers,
    )
    assert resp.status_code == 200
    report = resp.json()
    assert report["dry_run"] is False
    assert report["buckets_created"] == 2
    assert report["keywords_created"] == 3
    assert report["topics_inherited"] == 1

    wl = client.get("/v2/watchlist", headers=headers).json()
    assert wl["keyword_count"] == 3
    assert {b["name"] for b in wl["buckets"]} == {"Water Heaters", "Drains"}


def test_f4_t1_watchlist_get_returns_ordered_buckets_keywords_and_count(client, db, client_a):
    headers = admin_headers(client_a)
    b2 = seed_bucket(db, client_a, "Second Group", sort_order=2)
    b1 = seed_bucket(db, client_a, "First Group", sort_order=1)
    seed_kw(db, b1, client_a, "low volume term", volume=100)
    seed_kw(db, b1, client_a, "high volume term", volume=900)
    seed_kw(db, b2, client_a, "middle term", volume=500)
    db.commit()

    resp = client.get("/v2/watchlist", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["keyword_count"] == 3
    assert [b["name"] for b in data["buckets"]] == ["First Group", "Second Group"]
    assert [k["keyword"] for k in data["buckets"][0]["keywords"]] == [
        "high volume term",
        "low volume term",
    ]


# ── Group 4: F5 Watchlist GSC Suggestions (5 tests) ──────────────────────────


def test_f5_t1_suggestions_returns_gsc_connected_metadata_and_rows(client, db, client_a):
    set_integration(db, client_a, IntegrationProvider.GSC, "sc-domain:clienta.example")
    today = date.today() - timedelta(days=1)
    seed_gsc_query_page(
        db,
        client_a,
        today,
        "trenchless sewer repair",
        impressions=320,
        position=11.4,
        clicks=14,
        url="/services/trenchless",
    )
    db.commit()

    resp = client.get("/v2/watchlist/suggestions", headers=admin_headers(client_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["gsc_connected"] is True
    assert body["has_gsc_data"] is True
    assert body["google_through"] == today.isoformat()
    assert body["days"] == 90
    assert len(body["suggestions"]) == 1
    row = body["suggestions"][0]
    assert row["query"] == "trenchless sewer repair"
    assert row["impressions"] == 320
    assert row["clicks"] == 14
    assert isinstance(row["signals"], list)
    assert row["relevance_note"]


def test_f5_t1_suggestions_excludes_brand_and_brand_aliases(client, db, tier):
    c = make_client(
        db,
        tier,
        "Acme Plumbing",
        domain="acmeplumbing.example",
        brand_aliases=["acme hydro", "acme drain pros"],
    )
    set_integration(db, c, IntegrationProvider.GSC, "sc-domain:acmeplumbing.example")
    day = date.today() - timedelta(days=1)
    seed_gsc_query_page(db, c, day, "acme plumbing", impressions=500, position=1.5, clicks=80)
    seed_gsc_query_page(db, c, day, "acme hydro service", impressions=400, position=2.1, clicks=30)
    seed_gsc_query_page(db, c, day, "emergency pipe repair", impressions=250, position=8.0, clicks=12)
    db.commit()

    resp = client.get("/v2/watchlist/suggestions", headers=admin_headers(c))
    assert resp.status_code == 200
    queries = [s["query"] for s in resp.json()["suggestions"]]
    assert queries == ["emergency pipe repair"]


def test_f5_t1_suggestions_excludes_already_tracked_normalized_watchlist_keywords(
    client, db, client_a
):
    set_integration(db, client_a, IntegrationProvider.GSC, "sc-domain:clienta.example")
    bucket = seed_bucket(db, client_a, "Core")
    seed_kw(db, bucket, client_a, "  Sump Pump   Replacement ")
    day = date.today() - timedelta(days=1)
    seed_gsc_query_page(db, client_a, day, "sump pump replacement", impressions=400, position=7.2)
    seed_gsc_query_page(db, client_a, day, "french drain installation", impressions=300, position=9.5)
    db.commit()

    resp = client.get("/v2/watchlist/suggestions", headers=admin_headers(client_a))
    assert resp.status_code == 200
    queries = [s["query"] for s in resp.json()["suggestions"]]
    assert "sump pump replacement" not in queries
    assert "french drain installation" in queries


def test_f5_t1_suggestions_supports_search_filter_and_limit(client, db, client_a):
    set_integration(db, client_a, IntegrationProvider.GSC, "sc-domain:clienta.example")
    day = date.today() - timedelta(days=1)
    seed_gsc_query_page(db, client_a, day, "sewer scope camera", impressions=220, position=8.0)
    seed_gsc_query_page(db, client_a, day, "sewer main replacement", impressions=340, position=9.0)
    seed_gsc_query_page(db, client_a, day, "sewer backup cleanup", impressions=180, position=12.0)
    seed_gsc_query_page(db, client_a, day, "water softener install", impressions=500, position=6.0)
    db.commit()

    resp = client.get(
        "/v2/watchlist/suggestions",
        params={"search": "sewer", "limit": 2},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) == 2
    assert all("sewer" in s["query"].lower() for s in suggestions)


def test_f5_t1_adding_suggested_query_removes_it_from_subsequent_suggestions(client, db, client_a):
    headers = admin_headers(client_a)
    set_integration(db, client_a, IntegrationProvider.GSC, "sc-domain:clienta.example")
    day = date.today() - timedelta(days=1)
    seed_gsc_query_page(db, client_a, day, "slab leak detection", impressions=350, position=7.5)
    seed_gsc_query_page(db, client_a, day, "repiping specialist", impressions=210, position=10.2)
    db.commit()

    before = client.get("/v2/watchlist/suggestions", headers=headers).json()["suggestions"]
    assert {s["query"] for s in before} == {"slab leak detection", "repiping specialist"}

    add_resp = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "slab leak detection", "bucket_name": "Leak Detection"},
        headers=headers,
    )
    assert add_resp.status_code == 200
    assert add_resp.json()["created"] is True

    after = client.get("/v2/watchlist/suggestions", headers=headers).json()["suggestions"]
    assert [s["query"] for s in after] == ["repiping specialist"]


# ── Group 5: F6 Watchlist Multi-Tenancy & Normalization (5 tests) ────────────


def test_f6_t1_assigned_sma_team_user_can_crud_watchlist_and_view_suggestions(
    client, db, client_a
):
    make_user(
        db,
        email="specialist@smamarketing.com",
        role=UserRole.SMA_TEAM,
        assign_clients=[client_a],
    )
    set_integration(db, client_a, IntegrationProvider.GSC, "sc-domain:clienta.example")
    seed_gsc_query_page(
        db, client_a, date.today() - timedelta(days=1), "backflow testing", impressions=180, position=9.0
    )
    db.commit()

    headers = api_headers(client_a.id, "specialist@smamarketing.com")

    sugg = client.get("/v2/watchlist/suggestions", headers=headers)
    assert sugg.status_code == 200
    assert [s["query"] for s in sugg.json()["suggestions"]] == ["backflow testing"]

    created = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "backflow testing"},
        headers=headers,
    )
    assert created.status_code == 200
    kw_id = created.json()["id"]

    edited = client.patch(
        f"/v2/watchlist/keywords/{kw_id}",
        json={"volume": 450, "notes": "Assigned specialist edit"},
        headers=headers,
    )
    assert edited.status_code == 200
    assert edited.json()["volume"] == 450

    listed = client.get("/v2/watchlist", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["keyword_count"] == 1

    deleted = client.delete(f"/v2/watchlist/keywords/{kw_id}", headers=headers)
    assert deleted.status_code == 204


def test_f6_t1_add_keyword_without_bucket_auto_creates_general_bucket(client, db, client_a):
    headers = admin_headers(client_a)
    resp = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "commercial grease trap cleaning"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] is True
    assert data["bucket_created"] is True
    assert data["bucket_name"] == "General"

    wl = client.get("/v2/watchlist", headers=headers).json()
    assert len(wl["buckets"]) == 1
    assert wl["buckets"][0]["name"] == "General"
    assert wl["keyword_count"] == 1


def test_f6_t1_keyword_key_normalizes_extra_whitespace_and_casing(client, db, client_a):
    headers = admin_headers(client_a)
    resp = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "   Emergency   Plumber   Austin  "},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] is True
    assert data["keyword"] == "Emergency Plumber Austin"
    assert data["keyword_key"] == norm_key("Emergency Plumber Austin") == "emergency plumber austin"


def test_f6_t1_deleting_bucket_with_confirm_removes_keywords_and_updates_count(
    client, db, client_a
):
    headers = admin_headers(client_a)
    b1 = client.post("/v2/watchlist/buckets", json={"name": "Removable"}, headers=headers).json()
    b2 = client.post("/v2/watchlist/buckets", json={"name": "Kept"}, headers=headers).json()
    client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "term one", "bucket_id": b1["id"]},
        headers=headers,
    )
    client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "term two", "bucket_id": b1["id"]},
        headers=headers,
    )
    client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "term three", "bucket_id": b2["id"]},
        headers=headers,
    )

    del_resp = client.delete(
        f"/v2/watchlist/buckets/{b1['id']}",
        params={"confirm": "true"},
        headers=headers,
    )
    assert del_resp.status_code == 200
    d = del_resp.json()
    assert d["deleted"] is True
    assert d["deleted_keywords"] == 2

    wl = client.get("/v2/watchlist", headers=headers).json()
    assert wl["keyword_count"] == 1
    assert [b["name"] for b in wl["buckets"]] == ["Kept"]


def test_f6_t1_duplicate_keyword_post_is_idempotent_while_patch_updates_fields(
    client, db, client_a
):
    headers = admin_headers(client_a)
    first = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "Tankless Flush Service", "bucket_name": "Maintenance"},
        headers=headers,
    ).json()
    assert first["created"] is True

    dup = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "  tankless   flush service  ", "bucket_name": "Other"},
        headers=headers,
    ).json()
    assert dup["created"] is False
    assert dup["bucket_created"] is False
    assert dup["id"] == first["id"]

    patched = client.patch(
        f"/v2/watchlist/keywords/{first['id']}",
        json={"volume": 320, "intent": "informational", "notes": "Annual reminder"},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["volume"] == 320
    assert patched.json()["intent"] == "informational"
    assert patched.json()["notes"] == "Annual reminder"


# ── Group 6: F7 Content Gaps Filtering (6 tests) ─────────────────────────────


def _seed_plumbing_domain_site(db, client_obj):
    today = date.today()
    seed_indexable_site(db, client_obj, count=12, snap_date=today)
    bucket = seed_bucket(db, client_obj, "Plumbing Core")
    for kw in (
        "emergency plumbing repair",
        "water heater replacement",
        "drain cleaning service",
        "sewer line inspection",
        "slab leak detection",
        "pipe installation",
    ):
        seed_kw(db, bucket, client_obj, kw)
    db.commit()
    return today


def test_f7_t1_content_gaps_surfaces_relevant_priced_topic_gap(client, db, tier):
    c = make_client(db, tier, "Metro Plumbing", domain="metroplumbing.example")
    today = _seed_plumbing_domain_site(db, c)
    day = today - timedelta(days=5)

    seed_gsc_query_page(
        db,
        c,
        day,
        "trenchless sewer lining",
        impressions=260,
        position=19.0,
        clicks=5,
        url="/services/item-1",
    )
    seed_ser_metric(
        db, c, "trenchless sewer lining", volume=720, difficulty=28, intents=["commercial"]
    )
    db.commit()

    resp = client.get("/v2/content/gaps", headers=admin_headers(c))
    assert resp.status_code == 200
    body = resp.json()
    assert body["blocked"] is None
    terms = {g["term"]: g for g in body["gaps"]}
    assert "trenchless sewer lining" in terms
    gap = terms["trenchless sewer lining"]
    assert gap["priced"] is True
    assert gap["volume"] == 720
    assert gap["opportunity"] > 0


def test_f7_t1_content_gaps_filters_off_topic_unrelated_domain_queries(client, db, tier):
    c = make_client(db, tier, "Metro Plumbing", domain="metroplumbing.example")
    today = _seed_plumbing_domain_site(db, c)
    day = today - timedelta(days=5)

    seed_gsc_query_page(
        db, c, day, "trenchless sewer lining", impressions=240, position=18.0, url="/services/item-1"
    )
    seed_ser_metric(db, c, "trenchless sewer lining", volume=600, difficulty=25)

    seed_gsc_query_page(
        db, c, day, "vegan sourdough starter recipe", impressions=450, position=22.0, url="/services/item-1"
    )
    seed_ser_metric(db, c, "vegan sourdough starter recipe", volume=2400, difficulty=20)
    db.commit()

    resp = client.get("/v2/content/gaps", headers=admin_headers(c))
    assert resp.status_code == 200
    terms = {g["term"] for g in resp.json()["gaps"]}
    assert "trenchless sewer lining" in terms
    assert "vegan sourdough starter recipe" not in terms


def test_f7_t1_content_gaps_filters_navigational_and_utility_queries(client, db, tier):
    c = make_client(db, tier, "Metro Plumbing", domain="metroplumbing.example")
    today = _seed_plumbing_domain_site(db, c)
    day = today - timedelta(days=5)

    seed_gsc_query_page(
        db, c, day, "trenchless sewer lining", impressions=240, position=18.0, url="/services/item-1"
    )
    seed_ser_metric(db, c, "trenchless sewer lining", volume=600, difficulty=25)

    for utility_query in (
        "plumbing customer portal login",
        "plumbing privacy policy",
        "plumbing careers",
        "plumbing sign in",
        "plumbing customer service phone number",
    ):
        seed_gsc_query_page(
            db, c, day, utility_query, impressions=350, position=16.0, url="/services/item-1"
        )
        seed_ser_metric(db, c, utility_query, volume=900, difficulty=15)
    db.commit()

    resp = client.get("/v2/content/gaps", headers=admin_headers(c))
    assert resp.status_code == 200
    terms = {g["term"] for g in resp.json()["gaps"]}
    assert "trenchless sewer lining" in terms
    for utility_query in (
        "plumbing customer portal login",
        "plumbing privacy policy",
        "plumbing careers",
        "plumbing sign in",
        "plumbing customer service phone number",
    ):
        assert utility_query not in terms


def test_f7_t1_content_gaps_filters_short_brand_and_brand_aliases(client, db, tier):
    c = make_client(
        db,
        tier,
        "ZPX Plumbing",
        domain="zpx.example",
        brand_aliases=["metro hydro pros"],
    )
    today = _seed_plumbing_domain_site(db, c)
    day = today - timedelta(days=5)

    seed_gsc_query_page(
        db, c, day, "trenchless sewer lining", impressions=240, position=18.0, url="/services/item-1"
    )
    seed_ser_metric(db, c, "trenchless sewer lining", volume=600, difficulty=25)

    for brand_q in ("zpx sewer repair", "metro hydro pros plumbing"):
        seed_gsc_query_page(
            db, c, day, brand_q, impressions=300, position=15.0, url="/services/item-1"
        )
        seed_ser_metric(db, c, brand_q, volume=800, difficulty=15)
    db.commit()

    resp = client.get("/v2/content/gaps", headers=admin_headers(c))
    assert resp.status_code == 200
    terms = {g["term"] for g in resp.json()["gaps"]}
    assert "trenchless sewer lining" in terms
    assert "zpx sewer repair" not in terms
    assert "metro hydro pros plumbing" not in terms


def test_f7_t1_content_gaps_filters_rival_competitor_brand_terms(client, db, tier):
    c = make_client(
        db,
        tier,
        "Metro Plumbing",
        domain="metroplumbing.example",
        competitor_domains=["rotorooter.example", "beaconpipes.example"],
    )
    today = _seed_plumbing_domain_site(db, c)
    day = today - timedelta(days=5)

    seed_gsc_query_page(
        db, c, day, "trenchless sewer lining", impressions=240, position=18.0, url="/services/item-1"
    )
    seed_ser_metric(db, c, "trenchless sewer lining", volume=600, difficulty=25)

    seed_gsc_query_page(
        db, c, day, "rotorooter drain repair", impressions=320, position=17.0, url="/services/item-1"
    )
    seed_ser_metric(db, c, "rotorooter drain repair", volume=950, difficulty=22)

    seed_competitor_kw(
        db,
        c,
        "beaconpipes.example",
        "beaconpipes sewer replacement",
        position=3.0,
        fetched_at=today,
        volume=800,
        difficulty=25,
    )
    db.commit()

    resp = client.get("/v2/content/gaps", headers=admin_headers(c))
    assert resp.status_code == 200
    terms = {g["term"] for g in resp.json()["gaps"]}
    assert "trenchless sewer lining" in terms
    assert "rotorooter drain repair" not in terms
    assert "beaconpipes sewer replacement" not in terms


def test_f7_t1_content_gaps_filters_excluded_watch_targets_and_unpriced_noise(client, db, tier):
    c = make_client(db, tier, "Metro Plumbing", domain="metroplumbing.example")
    today = _seed_plumbing_domain_site(db, c)
    day = today - timedelta(days=5)

    seed_gsc_query_page(
        db, c, day, "trenchless sewer lining", impressions=240, position=18.0, url="/services/item-1"
    )
    seed_ser_metric(db, c, "trenchless sewer lining", volume=600, difficulty=25)

    seed_gsc_query_page(
        db, c, day, "cast iron pipe descaling", impressions=280, position=16.0, url="/services/item-1"
    )
    seed_ser_metric(db, c, "cast iron pipe descaling", volume=550, difficulty=24)
    seed_watch_target_excluded(db, c, "cast iron pipe descaling")

    # Seed topical anchor in watchlist so "hydronic" passes topical relevance without
    # being covered by crawl titles/H1s, exercising content_gaps_view's unpriced-waiting filter
    # (WAITING_MIN_IMPRESSIONS=200 & len(words) < 2 with clicks < 2).
    extra_bucket = seed_bucket(db, c, "Hydronic Heating")
    seed_kw(db, extra_bucket, c, "hydronic boiler maintenance")
    seed_gsc_query_page(
        db, c, day, "hydronic", impressions=110, clicks=0, position=18.0, url="/services/item-1"
    )
    db.commit()

    resp = client.get("/v2/content/gaps", headers=admin_headers(c))
    assert resp.status_code == 200
    terms = {g["term"] for g in resp.json()["gaps"]}
    assert "trenchless sewer lining" in terms
    assert "cast iron pipe descaling" not in terms
    assert "hydronic" not in terms


# ── Group 7: F8 Content Optimizer Ad-Hoc Keyword (6 tests) ───────────────────


def test_f8_t1_optimizer_ad_hoc_keyword_with_text_succeeds_without_gsc_or_watchlist(
    client, db, client_a, stub_optimizer_llm
):
    target_url = f"https://{client_a.domain}/services/trenchless-sewer"
    page_text = (
        "Trenchless Sewer Solutions\n\n"
        "Our certified plumbers restore damaged underground pipes without excavating your yard or driveway.\n\n"
        "We complete camera diagnostics and structural pipe lining in a single business day."
    )
    db.commit()

    draft = client.post(
        "/v2/optimizer/draft",
        json={
            "url": target_url,
            "kind": "opening",
            "depth": "quick",
            "text": page_text,
            "keyword": "trenchless sewer repair",
        },
        headers=admin_headers(client_a),
    )
    assert draft.status_code == 202
    assert draft.json()["id"]

    page = client.get(
        "/v2/optimizer/page",
        params={"url": target_url},
        headers=admin_headers(client_a),
    )
    assert page.status_code == 200
    data = page.json()
    assert data["searches_total"] == 0
    opening = data["drafts"]["opening"]
    assert opening is not None
    assert opening["status"] == "done"
    assert len(opening["options"]) >= 1


def test_f8_t1_optimizer_preserves_ad_hoc_keyword_in_opening_draft_payload(
    client, db, client_a, stub_optimizer_llm
):
    target_url = f"https://{client_a.domain}/services/hydro-jetting"
    page_text = (
        "High-Pressure Drain Cleaning\n\n"
        "High-pressure water streams clear stubborn grease and tree roots from commercial sewer lines safely."
    )
    db.commit()

    resp = client.post(
        "/v2/optimizer/draft",
        json={
            "url": target_url,
            "kind": "opening",
            "depth": "quick",
            "text": page_text,
            "keyword": "  hydro   jetting drain cleaning ",
        },
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 202

    page = client.get(
        "/v2/optimizer/page",
        params={"url": target_url},
        headers=admin_headers(client_a),
    ).json()
    opening = page["drafts"]["opening"]
    assert opening["status"] == "done"
    assert opening["keyword"] == "hydro jetting drain cleaning"


def test_f8_t1_optimizer_ad_hoc_keyword_works_for_terms_with_verbatim_text(
    client, db, client_a, stub_optimizer_llm
):
    target_url = f"https://{client_a.domain}/services/water-softener"
    page_text = (
        "Whole-Home Water Conditioning\n\n"
        "Our technicians install high-efficiency filtration equipment tailored to local municipal water hardness."
    )
    db.commit()

    resp = client.post(
        "/v2/optimizer/draft",
        json={
            "url": target_url,
            "kind": "terms",
            "depth": "quick",
            "text": page_text,
            "keyword": "hard water softener installation",
        },
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 202

    page = client.get(
        "/v2/optimizer/page",
        params={"url": target_url},
        headers=admin_headers(client_a),
    ).json()
    terms_draft = page["drafts"]["terms"]
    assert terms_draft["status"] == "done"
    assert terms_draft["keyword"] == "hard water softener installation"
    assert len(terms_draft["edits"]) >= 1
    assert terms_draft["edits"][0]["before"] in " ".join(page_text.split())


def test_f8_t1_optimizer_ad_hoc_keyword_works_for_faq(
    client, db, client_a, stub_optimizer_llm
):
    target_url = f"https://{client_a.domain}/services/sump-pump"
    page_text = (
        "Basement Flood Prevention\n\n"
        "Backup sump pump systems protect finished basements during heavy storms and power outages."
    )
    db.commit()

    resp = client.post(
        "/v2/optimizer/draft",
        json={
            "url": target_url,
            "kind": "faq",
            "depth": "quick",
            "text": page_text,
            "keyword": "battery backup sump pump installation",
        },
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 202

    page = client.get(
        "/v2/optimizer/page",
        params={"url": target_url},
        headers=admin_headers(client_a),
    ).json()
    faq_draft = page["drafts"]["faq"]
    assert faq_draft["status"] == "done"
    assert faq_draft["keyword"] == "battery backup sump pump installation"
    assert len(faq_draft["items"]) >= 1
    assert '"FAQPage"' in faq_draft["markup"]


def test_f8_t1_optimizer_ad_hoc_keyword_uses_crawl_sections_when_text_omitted(
    client, db, client_a, stub_optimizer_llm
):
    base_url = f"https://{client_a.domain}"
    path = "/services/tankless-flush"
    sections = [
        {
            "level": 1,
            "heading": "Tankless Water Heater Maintenance",
            "first_paragraph": (
                "Annual descaling removes mineral buildup inside heat exchangers and preserves manufacturer warranties."
            ),
        },
        {
            "level": 2,
            "heading": "Inspection Checklist",
            "first_paragraph": (
                "Every maintenance visit tests flow sensors, flushes inlet screens, and verifies venting safety."
            ),
        },
    ]
    full_url = seed_crawl_page(
        db,
        client_a,
        base_url,
        path,
        date.today(),
        title="Tankless Water Heater Maintenance",
        desc="Annual tankless descaling and inspection.",
        sections=sections,
    )
    db.commit()

    for kind in ("opening", "faq"):
        draft_resp = client.post(
            "/v2/optimizer/draft",
            json={
                "url": full_url,
                "kind": kind,
                "depth": "quick",
                "keyword": "tankless water heater descaling",
            },
            headers=admin_headers(client_a),
        )
        assert draft_resp.status_code == 202

    page = client.get(
        "/v2/optimizer/page",
        params={"url": full_url},
        headers=admin_headers(client_a),
    ).json()
    assert page["drafts"]["opening"]["status"] == "done"
    assert page["drafts"]["opening"]["source"]["kind"] == "crawl"
    assert page["drafts"]["faq"]["status"] == "done"
    assert page["drafts"]["faq"]["source"]["kind"] == "crawl"


def test_f8_t1_optimizer_queue_reflects_model_ready_and_kinds(
    client, db, client_a, stub_optimizer_llm
):
    resp = client.get("/v2/optimizer", headers=admin_headers(client_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_ready"] is True
    assert set(body["kinds"]) == {"opening", "terms", "faq"}
    assert isinstance(body["queue"], list)


# ── Group 8: F9 Content Sources Sitemap-Only Cleanup (5 tests) ───────────────


def test_f9_t1_get_v2_feeds_returns_404(client, db, client_a):
    resp = client.get("/v2/feeds", headers=admin_headers(client_a))
    assert resp.status_code == 404


def test_f9_t1_post_v2_feeds_returns_404(client, db, client_a):
    resp = client.post(
        "/v2/feeds",
        json={"feed_url": f"https://{client_a.domain}/feed.xml"},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 404


def test_f9_t1_patch_client_updates_sitemap_url_and_persists(client, db, client_a):
    headers = admin_headers(client_a)
    sitemap = f"https://{client_a.domain}/sitemap_index.xml"
    patch_resp = client.patch(
        f"/clients/{client_a.id}",
        json={"sitemap_url": sitemap},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["sitemap_url"] == sitemap

    get_resp = client.get(f"/clients/{client_a.id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["sitemap_url"] == sitemap


def test_f9_t1_patch_client_clears_sitemap_url_cleanly(client, db, tier):
    c = make_client(
        db, tier, "Sitemap Clear Client", sitemap_url="https://sitemapclear.example/sitemap.xml"
    )
    headers = admin_headers(c)
    assert client.get(f"/clients/{c.id}", headers=headers).json()["sitemap_url"]

    patch_resp = client.patch(
        f"/clients/{c.id}",
        json={"sitemap_url": None},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["sitemap_url"] is None

    get_resp = client.get(f"/clients/{c.id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["sitemap_url"] is None


def test_f9_t1_content_gaps_and_setup_remain_healthy_without_feeds(client, db, tier):
    c = make_client(
        db, tier, "Healthy Sitemap Only Co", sitemap_url="https://healthyonly.example/sitemap.xml"
    )
    seed_indexable_site(db, c, count=12, snap_date=date.today())

    setup_resp = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c))
    assert setup_resp.status_code == 200
    assert "content_sources" not in _step_map(setup_resp.json())

    gaps_resp = client.get("/v2/content/gaps", headers=admin_headers(c))
    assert gaps_resp.status_code == 200
    assert gaps_resp.json()["blocked"] is None


# ── Group 9: F10/F11 All-Clients Overview (6 tests) ──────────────────────────


def test_f10_t1_overview_returns_window_and_all_accessible_clients(client, db, tier):
    c1 = make_client(db, tier, "Alpha Overview")
    c2 = make_client(db, tier, "Beta Overview")

    resp = client.get("/v2/clients/overview", headers=api_headers(email="admin@smamarketing.com"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["window"]["days"] == 30
    ids = {item["id"] for item in body["clients"]}
    assert {str(c1.id), str(c2.id)}.issubset(ids)


def test_f10_t1_overview_aggregates_30d_gsc_visibility_and_change_pct(client, db, tier):
    c = make_client(db, tier, "Visibility Metrics Co")
    as_of = date.today() - timedelta(days=1)
    seed_gsc_daily(db, c, as_of - timedelta(days=5), impressions=1000, clicks=50, position=6.0)
    seed_gsc_daily(db, c, as_of - timedelta(days=2), impressions=2000, clicks=100, position=9.0)
    # Prior 30d: [as_of - 59, as_of - 30]
    seed_gsc_daily(db, c, as_of - timedelta(days=35), impressions=1500, clicks=40, position=10.0)
    db.commit()

    resp = client.get(
        "/v2/clients/overview",
        params={"as_of": as_of.isoformat()},
        headers=api_headers(email="admin@smamarketing.com"),
    )
    assert resp.status_code == 200
    item = next(x for x in resp.json()["clients"] if x["id"] == str(c.id))
    assert item["impressions"] == 3000
    assert item["clicks"] == 150
    # Weighted avg position: (1000*6 + 2000*9) / 3000 = 8.0
    assert item["avg_position"] == 8.0
    # Change pct: (3000 - 1500) / 1500 * 100 = 100.0
    assert item["impressions_change_pct"] == 100.0


def test_f10_t1_overview_aggregates_30d_ga4_traffic_and_organic_change_pct(client, db, tier):
    c = make_client(db, tier, "Traffic Metrics Co")
    as_of = date.today() - timedelta(days=1)
    seed_ga4_traffic(db, c, as_of - timedelta(days=3), 600, channel=OrganicChannel.ORGANIC_SEARCH, url="/")
    seed_ga4_traffic(
        db, c, as_of - timedelta(days=3), 250, channel=OrganicChannel.DIRECT_UNATTRIBUTED, url="/"
    )
    seed_ga4_traffic(db, c, as_of - timedelta(days=35), 400, channel=OrganicChannel.ORGANIC_SEARCH, url="/")
    db.commit()

    resp = client.get(
        "/v2/clients/overview",
        params={"as_of": as_of.isoformat()},
        headers=api_headers(email="admin@smamarketing.com"),
    )
    assert resp.status_code == 200
    item = next(x for x in resp.json()["clients"] if x["id"] == str(c.id))
    assert item["total_sessions"] == 850
    assert item["organic_sessions"] == 600
    # Change pct: (600 - 400) / 400 * 100 = 50.0
    assert item["organic_change_pct"] == 50.0


def test_f10_t1_overview_aggregates_30d_leads_minus_exclusions(client, db, tier):
    c = make_client(db, tier, "Leads Exclusion Co")
    as_of = date.today() - timedelta(days=1)
    seed_conversion_def(db, c, event_name="generate_lead", conversion_type="lead", active=True)
    seed_conversion_def(db, c, event_name="spam_event", conversion_type="lead", active=True)
    seed_conversion_def(db, c, event_name="scroll_depth", conversion_type="engagement", active=True)

    seed_lead_exclusion(db, c, reason="test form", url_pattern=f"https://{c.domain}/test-form*")
    seed_lead_exclusion(db, c, reason="spam event", event_name="spam_event")

    cur_day = as_of - timedelta(days=4)
    seed_ga4_event(db, c, cur_day, "generate_lead", 18, url="/contact")
    seed_ga4_event(db, c, cur_day, "generate_lead", 5, url="/test-form-staging")
    seed_ga4_event(db, c, cur_day, "spam_event", 9, url="/contact")
    seed_ga4_event(db, c, cur_day, "scroll_depth", 40, url="/contact")
    db.commit()

    resp = client.get(
        "/v2/clients/overview",
        params={"as_of": as_of.isoformat()},
        headers=api_headers(email="admin@smamarketing.com"),
    )
    assert resp.status_code == 200
    item = next(x for x in resp.json()["clients"] if x["id"] == str(c.id))
    assert item["leads"] == 18


def test_f10_t1_overview_includes_client_metadata_and_freshness_dates(client, db, tier):
    c = make_client(
        db,
        tier,
        "Metadata Overview Co",
        domain="metadataoverview.example",
        status=ClientStatus.ONBOARDING,
        service_mode="consulting",
        monthly_lead_goal=33,
    )
    as_of = date.today() - timedelta(days=1)
    gsc_day = as_of - timedelta(days=2)
    ga4_day = as_of - timedelta(days=1)
    seed_gsc_daily(db, c, gsc_day, impressions=100, clicks=5, position=7.0)
    seed_ga4_traffic(db, c, ga4_day, 120, channel=OrganicChannel.ORGANIC_SEARCH, url="/")
    db.commit()

    resp = client.get(
        "/v2/clients/overview",
        params={"as_of": as_of.isoformat()},
        headers=api_headers(email="admin@smamarketing.com"),
    )
    assert resp.status_code == 200
    item = next(x for x in resp.json()["clients"] if x["id"] == str(c.id))
    assert item["id"] == str(c.id)
    assert item["client_name"] == "Metadata Overview Co"
    assert item["slug"] == c.slug
    assert item["domain"] == "metadataoverview.example"
    assert item["status"] == "onboarding"
    assert item["service_mode"] == "consulting"
    assert item["monthly_lead_goal"] == 33
    assert item["gsc_through"] == gsc_day.isoformat()
    assert item["ga4_through"] == ga4_day.isoformat()


def test_f10_t1_overview_scopes_sma_admin_to_all_and_sma_team_to_assigned(client, db, tier):
    c_assigned = make_client(db, tier, "Assigned Team Client")
    c_unassigned = make_client(db, tier, "Unassigned Client")
    make_user(
        db,
        email="scoped_team@smamarketing.com",
        role=UserRole.SMA_TEAM,
        assign_clients=[c_assigned],
    )

    admin_resp = client.get(
        "/v2/clients/overview", headers=api_headers(email="admin@smamarketing.com")
    )
    assert admin_resp.status_code == 200
    admin_ids = {item["id"] for item in admin_resp.json()["clients"]}
    assert {str(c_assigned.id), str(c_unassigned.id)}.issubset(admin_ids)

    team_resp = client.get(
        "/v2/clients/overview", headers=api_headers(email="scoped_team@smamarketing.com")
    )
    assert team_resp.status_code == 200
    team_ids = {item["id"] for item in team_resp.json()["clients"]}
    assert team_ids == {str(c_assigned.id)}
