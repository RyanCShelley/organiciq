"""Tier 3 E2E Tests: Pairwise cross-feature combination tests for Phase 4."""

from __future__ import annotations

from datetime import date, timedelta

from app.models.client import ClientStatus
from app.models.config import OrganicChannel
from app.models.integration import IntegrationProvider
from app.models.user import UserRole
from e2e_phase4.conftest import (
    _shift_month,
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
    seed_watch_target_excluded,
    set_integration,
)


def _step_map(setup_payload: dict) -> dict[str, dict]:
    return {step["key"]: step for step in setup_payload["steps"]}


# ── Pair 1: Guided Setup + Baseline Lock ──────────────────────────────────────


def test_t3_pair_setup_and_baseline_lock(client, db, tier, admin_user):
    c = make_client(db, tier, "Setup Baseline Pair Co")
    set_integration(db, c, IntegrationProvider.GA4, "properties/1001")
    set_integration(db, c, IntegrationProvider.GSC, "sc-domain:setupbaseline.example")
    through = seed_ga4_baseline_window(
        db,
        c,
        months=7,
        sessions_per_month=1100,
        direct_sessions_per_month=300,
        leads_per_month=14,
    )
    seed_gsc_page(db, c, through, "/services/item-1", impressions=900, clicks=40, position=8.0)
    db.commit()

    before = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c))
    assert before.status_code == 200
    before_body = before.json()
    before_steps = _step_map(before_body)
    assert before_steps["baseline"]["done"] is False
    assert before_body["next"] == "baseline"

    lock_res = client.post(
        f"/clients/{c.id}/baseline/lock",
        headers=admin_headers(c),
        json={"source": "ga4", "months": 24, "half_life_months": 3.0},
    )
    assert lock_res.status_code == 200, lock_res.text
    locked = lock_res.json()

    after = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c))
    assert after.status_code == 200
    after_body = after.json()
    after_steps = _step_map(after_body)
    assert after_steps["baseline"]["done"] is True
    assert after_body["done"] == before_body["done"] + 1
    assert after_body["next"] != "baseline"
    assert f"{locked['monthly_lead_goal']}/mo" in after_steps["baseline"]["detail"]


# ── Pair 2: Guided Setup + Watchlist Add ──────────────────────────────────────


def test_t3_pair_setup_and_watchlist_add(client, db, tier, admin_user):
    c = make_client(db, tier, "Setup Watchlist Pair Co")
    set_integration(db, c, IntegrationProvider.GA4, "properties/1002")
    set_integration(db, c, IntegrationProvider.GSC, "sc-domain:setupwatchlist.example")
    through = seed_ga4_baseline_window(db, c, months=7, leads_per_month=12)
    seed_gsc_page(db, c, through, "/", impressions=600, clicks=25, position=9.5)
    db.commit()

    lock_res = client.post(
        f"/clients/{c.id}/baseline/lock",
        headers=admin_headers(c),
        json={"source": "ga4", "months": 24},
    )
    assert lock_res.status_code == 200

    before = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c)).json()
    assert _step_map(before)["watchlist"]["done"] is False
    assert before["next"] == "watchlist"

    add_res = client.post(
        "/v2/watchlist/keywords",
        headers=admin_headers(c),
        json={"keyword": "commercial hvac maintenance", "bucket_name": "Core Services"},
    )
    assert add_res.status_code == 200, add_res.text
    assert add_res.json()["created"] is True

    after = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c)).json()
    after_steps = _step_map(after)
    assert after_steps["watchlist"]["done"] is True
    assert "1 keyword" in after_steps["watchlist"]["detail"]
    assert after["done"] == before["done"] + 1
    assert after["next"] == "first_run"


# ── Pair 3: Guided Setup + Sitemap Update ─────────────────────────────────────


def test_t3_pair_setup_and_sitemap_update(client, db, tier, admin_user):
    c = make_client(db, tier, "Setup Sitemap Pair Co")

    before = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c))
    assert before.status_code == 200
    before_body = before.json()
    before_keys = [s["key"] for s in before_body["steps"]]
    assert "content_sources" not in before_keys
    assert "conversion_pages" not in before_keys

    patch_res = client.patch(
        f"/clients/{c.id}",
        headers=admin_headers(c),
        json={"sitemap_url": f"https://{c.domain}/sitemap_index.xml"},
    )
    assert patch_res.status_code == 200, patch_res.text
    assert patch_res.json()["sitemap_url"] == f"https://{c.domain}/sitemap_index.xml"

    after = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c))
    assert after.status_code == 200
    after_body = after.json()
    assert after_body["done"] == before_body["done"]
    assert after_body["total"] == before_body["total"]
    assert after_body["next"] == before_body["next"]


# ── Pair 4: GSC Suggestions + Watchlist CRUD Add/Edit/Delete ──────────────────


def test_t3_pair_gsc_suggestions_and_watchlist_crud(client, db, tier, admin_user):
    c = make_client(db, tier, "Suggestions CRUD Pair Co", brand_aliases=["suggestions crud"])
    set_integration(db, c, IntegrationProvider.GSC, "sc-domain:suggestionscrud.example")
    today = date.today()
    seed_indexable_site(db, c, count=10, snap_date=today - timedelta(days=2))
    seed_gsc_query_page(
        db,
        c,
        today - timedelta(days=2),
        "emergency pipe repair",
        impressions=550,
        position=8.2,
        clicks=21,
        url="/services/item-1",
    )
    seed_gsc_query_page(
        db,
        c,
        today - timedelta(days=2),
        "drain snake rental",
        impressions=380,
        position=10.5,
        clicks=9,
        url="/services/item-2",
    )
    db.commit()

    sugg_1 = client.get("/v2/watchlist/suggestions", headers=admin_headers(c))
    assert sugg_1.status_code == 200
    keys_1 = {s["key"] for s in sugg_1.json()["suggestions"]}
    assert "emergency pipe repair" in keys_1
    assert "drain snake rental" in keys_1

    added = client.post(
        "/v2/watchlist/keywords",
        headers=admin_headers(c),
        json={"keyword": "emergency pipe repair", "bucket_name": "Urgent"},
    )
    assert added.status_code == 200
    kw_id = added.json()["id"]

    sugg_2 = client.get("/v2/watchlist/suggestions", headers=admin_headers(c))
    assert sugg_2.status_code == 200
    keys_2 = {s["key"] for s in sugg_2.json()["suggestions"]}
    assert "emergency pipe repair" not in keys_2
    assert "drain snake rental" in keys_2

    edited = client.patch(
        f"/v2/watchlist/keywords/{kw_id}",
        headers=admin_headers(c),
        json={"keyword": "copper pipe repair", "volume": 1200, "difficulty": 33},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["keyword"] == "copper pipe repair"

    # Original GSC query is no longer tracked -> reappears in suggestions.
    sugg_3 = client.get("/v2/watchlist/suggestions", headers=admin_headers(c))
    assert sugg_3.status_code == 200
    assert "emergency pipe repair" in {s["key"] for s in sugg_3.json()["suggestions"]}

    # Add again and delete -> disappears then reappears cleanly.
    added_again = client.post(
        "/v2/watchlist/keywords",
        headers=admin_headers(c),
        json={"keyword": "emergency pipe repair", "bucket_name": "Urgent"},
    )
    assert added_again.status_code == 200
    kw_id_2 = added_again.json()["id"]
    assert "emergency pipe repair" not in {
        s["key"] for s in client.get("/v2/watchlist/suggestions", headers=admin_headers(c)).json()["suggestions"]
    }

    deleted = client.delete(f"/v2/watchlist/keywords/{kw_id_2}", headers=admin_headers(c))
    assert deleted.status_code == 204
    assert "emergency pipe repair" in {
        s["key"] for s in client.get("/v2/watchlist/suggestions", headers=admin_headers(c)).json()["suggestions"]
    }


# ── Pair 5: Watchlist Add + Content Optimizer Ad-Hoc & Watchlist Keyword ──────


def test_t3_pair_watchlist_and_optimizer_adhoc(client, db, tier, admin_user, stub_optimizer_llm):
    c = make_client(db, tier, "Watchlist Optimizer Pair Co")
    today = date.today()
    unranked_url = seed_crawl_page(
        db,
        c,
        f"https://{c.domain}",
        "/services/trenchless-lining",
        today - timedelta(days=1),
        title="Trenchless Pipe Lining",
        desc="Structural pipe lining without excavation.",
        sections=[
            {
                "level": 1,
                "heading": "Trenchless Pipe Lining",
                "first_paragraph": (
                    "Our crew restores cracked underground sewer lines using cured-in-place pipe "
                    "lining without tearing up landscaping or driveways."
                ),
            }
        ],
    )
    db.commit()

    wl_res = client.post(
        "/v2/watchlist/keywords",
        headers=admin_headers(c),
        json={"keyword": "water heater installation", "bucket_name": "Plumbing Core"},
    )
    assert wl_res.status_code == 200

    # Ad-hoc keyword not on watchlist and with zero GSC data runs cleanly.
    adhoc_draft = client.post(
        "/v2/optimizer/draft",
        headers=admin_headers(c),
        json={
            "url": unranked_url,
            "kind": "opening",
            "depth": "quick",
            "keyword": "tankless heater retrofit",
        },
    )
    assert adhoc_draft.status_code == 202, adhoc_draft.text

    page_res = client.get(
        "/v2/optimizer/page",
        headers=admin_headers(c),
        params={"url": unranked_url},
    )
    assert page_res.status_code == 200
    opening = page_res.json()["drafts"]["opening"]
    assert opening is not None
    assert opening["status"] == "done"
    assert opening["keyword"] == "tankless heater retrofit"
    assert len(opening["options"]) >= 1

    # Watchlist keyword also runs cleanly on another optimizer kind (faq).
    wl_draft = client.post(
        "/v2/optimizer/draft",
        headers=admin_headers(c),
        json={
            "url": unranked_url,
            "kind": "faq",
            "depth": "quick",
            "keyword": "water heater installation",
        },
    )
    assert wl_draft.status_code == 202
    faq_res = client.get(
        "/v2/optimizer/page",
        headers=admin_headers(c),
        params={"url": unranked_url},
    ).json()["drafts"]["faq"]
    assert faq_res["status"] == "done"
    assert faq_res["keyword"] == "water heater installation"
    assert len(faq_res["items"]) >= 1


# ── Pair 6: Content Gaps Ignore / WatchTarget Exclusion + Search q ────────────


def test_t3_pair_content_gaps_exclusion_and_search_q(client, db, tier, admin_user):
    c = make_client(db, tier, "Gaps Filter Search Pair Co")
    recent = date.today() - timedelta(days=3)
    seed_indexable_site(db, c, count=11, snap_date=recent)
    seed_crawl_page(
        db,
        c,
        f"https://{c.domain}",
        "/services/plumbing-sewer",
        recent,
        title="Plumbing Sewer Pipe Line Service",
        desc="Hydro sewer pipe repair and plumbing line service.",
    )
    wl_bucket = seed_bucket(db, c, "Plumbing Sewer")
    seed_kw(db, wl_bucket, c, "sewer pipe repair")
    seed_kw(db, wl_bucket, c, "hydro line service")

    seed_gsc_query_page(db, c, recent, "hydro jetting sewer line", 420, 12.0, clicks=10, url="/services/item-1")
    seed_ser_metric(db, c, "hydro jetting sewer line", volume=800, difficulty=30)

    seed_gsc_query_page(db, c, recent, "trenchless pipe lining", 390, 14.0, clicks=8, url="/services/item-2")
    seed_ser_metric(db, c, "trenchless pipe lining", volume=650, difficulty=25)

    seed_gsc_query_page(db, c, recent, "free hydro jetting coupon", 310, 16.0, clicks=4, url="/services/item-3")
    seed_ser_metric(db, c, "free hydro jetting coupon", volume=500, difficulty=20)
    seed_watch_target_excluded(db, c, "free hydro jetting coupon")
    db.commit()

    initial = client.get("/v2/content/gaps", headers=admin_headers(c)).json()
    initial_terms = {g["term"] for g in initial["gaps"]}
    assert "hydro jetting sewer line" in initial_terms
    assert "trenchless pipe lining" in initial_terms
    assert "free hydro jetting coupon" not in initial_terms

    ign = client.post(
        "/v2/content/ignore",
        headers=admin_headers(c),
        json={"area": "gap", "key": "hydro jetting sewer line"},
    )
    assert ign.status_code == 200

    q_hydro = client.get("/v2/content/gaps", headers=admin_headers(c), params={"q": "hydro"}).json()
    assert q_hydro["gaps"] == []

    q_trench = client.get("/v2/content/gaps", headers=admin_headers(c), params={"q": "trenchless"}).json()
    assert [g["term"] for g in q_trench["gaps"]] == ["trenchless pipe lining"]

    q_ignored = client.get(
        "/v2/content/gaps",
        headers=admin_headers(c),
        params={"q": "hydro", "ignored": "true"},
    ).json()
    assert [g["term"] for g in q_ignored["gaps"]] == ["hydro jetting sewer line"]


# ── Pair 7: Sitemap PATCH + Optimizer + /v2/feeds 404 Coexistence ─────────────


def test_t3_pair_sitemap_optimizer_and_feeds_404_coexistence(client, db, tier, admin_user, stub_optimizer_llm):
    c = make_client(db, tier, "Sitemap Optimizer Feeds Co")
    recent = date.today() - timedelta(days=2)
    target_url = seed_crawl_page(
        db,
        c,
        f"https://{c.domain}",
        "/services/water-filtration",
        recent,
        title="Whole Home Water Filtration",
        sections=[
            {
                "level": 1,
                "heading": "Whole Home Water Filtration",
                "first_paragraph": "Clean drinking water throughout every faucet in your house.",
            }
        ],
    )
    db.commit()

    new_sitemap = f"https://{c.domain}/custom-sitemap.xml"
    patch_res = client.patch(f"/clients/{c.id}", headers=admin_headers(c), json={"sitemap_url": new_sitemap})
    assert patch_res.status_code == 200
    assert patch_res.json()["sitemap_url"] == new_sitemap

    feeds_get = client.get("/v2/feeds", headers=admin_headers(c))
    assert feeds_get.status_code == 404
    feeds_post = client.post(
        "/v2/feeds",
        headers=admin_headers(c),
        json={"url": f"https://{c.domain}/feed.xml"},
    )
    assert feeds_post.status_code == 404

    opt = client.post(
        "/v2/optimizer/draft",
        headers=admin_headers(c),
        json={"url": target_url, "kind": "opening", "keyword": "whole house water filter"},
    )
    assert opt.status_code == 202
    page = client.get("/v2/optimizer/page", headers=admin_headers(c), params={"url": target_url}).json()
    assert page["drafts"]["opening"]["status"] == "done"

    client_get = client.get(f"/clients/{c.id}", headers=admin_headers(c))
    assert client_get.status_code == 200
    assert client_get.json()["sitemap_url"] == new_sitemap


# ── Pair 8: Baseline Goal + All-Clients Overview ──────────────────────────────


def test_t3_pair_baseline_goal_and_clients_overview(client, db, tier, admin_user):
    c = make_client(db, tier, "Goal Overview Pair Co", monthly_lead_goal=20)
    seed_ga4_baseline_window(db, c, months=7, leads_per_month=15)
    db.commit()

    lock_res = client.post(
        f"/clients/{c.id}/baseline/lock",
        headers=admin_headers(c),
        json={"source": "ga4", "months": 24},
    )
    assert lock_res.status_code == 200

    goal_res = client.post(
        f"/clients/{c.id}/baseline/goal",
        headers=admin_headers(c),
        json={"monthly_lead_goal": 77},
    )
    assert goal_res.status_code == 200
    assert goal_res.json()["current"] == 77

    overview = client.get("/v2/clients/overview", headers=admin_headers(c))
    assert overview.status_code == 200
    row = next(item for item in overview.json()["clients"] if item["id"] == str(c.id))
    v1_detail = client.get(f"/clients/{c.id}/baseline/versions/1", headers=admin_headers(c)).json()
    cp3 = next(cp for cp in v1_detail["snapshot"]["projection"]["checkpoints"] if cp["month"] == 3)
    baseline_floor = int(round(v1_detail["snapshot"]["baseline"]["monthly_leads"]))
    expected_cp3_goal = max(int(round(cp3["monthly_leads"])), baseline_floor)
    assert row["monthly_lead_goal"] == 77
    assert row["current_lead_goal"] == expected_cp3_goal
    assert row["current_lead_goal"] > 0


# ── Pair 9: LeadExclusion + ConversionDefinition + Overview Leads ─────────────


def test_t3_pair_lead_exclusion_conversion_def_and_overview(client, db, tier, admin_user):
    c = make_client(db, tier, "Leads Exclusion Overview Co", business_model="lead_gen")
    recent = date.today() - timedelta(days=2)
    seed_ga4_traffic(db, c, recent, 500, channel=OrganicChannel.ORGANIC_SEARCH, url="/services/main")

    seed_conversion_def(db, c, "generate_lead", conversion_type="lead", active=True, is_primary=True)
    seed_conversion_def(db, c, "legacy_lead", conversion_type="lead", active=False, is_primary=False)
    seed_conversion_def(db, c, "scroll_90", conversion_type="engagement", active=True, is_primary=False)
    seed_lead_exclusion(db, c, url_pattern=f"https://{c.domain}/qa-test*", reason="QA form traffic")

    # 12 valid leads + 6 excluded leads + 4 inactive-def events + 25 engagement events
    seed_ga4_event(db, c, recent, "generate_lead", 12, url="/services/main")
    seed_ga4_event(db, c, recent, "generate_lead", 6, url="/qa-test/submit")
    seed_ga4_event(db, c, recent, "legacy_lead", 4, url="/services/main")
    seed_ga4_event(db, c, recent, "scroll_90", 25, url="/services/main")
    db.commit()

    overview = client.get("/v2/clients/overview", headers=admin_headers(c))
    assert overview.status_code == 200
    row = next(item for item in overview.json()["clients"] if item["id"] == str(c.id))
    assert row["leads"] == 12
    assert row["lead_label"] == "leads"


# ── Pair 10: UserClient Scoping Across Overview, Watchlist, Setup, Gaps, Opt ──


def test_t3_pair_user_client_scoping_across_features(client, db, tier):
    c_allowed = make_client(db, tier, "Scoped Allowed Co")
    c_hidden = make_client(db, tier, "Scoped Hidden Co")
    recent = date.today() - timedelta(days=2)
    seed_indexable_site(db, c_allowed, count=10, snap_date=recent)
    seed_indexable_site(db, c_hidden, count=10, snap_date=recent)
    team = make_user(db, email="scoped-team@smamarketing.com", role=UserRole.SMA_TEAM, assign_clients=[c_allowed])

    overview = client.get("/v2/clients/overview", headers=api_headers(email=team.email))
    assert overview.status_code == 200
    returned_ids = {item["id"] for item in overview.json()["clients"]}
    assert returned_ids == {str(c_allowed.id)}

    for path in (
        f"/clients/{c_allowed.id}/setup",
        "/v2/watchlist",
        "/v2/watchlist/suggestions",
        "/v2/content/gaps",
        "/v2/optimizer",
    ):
        ok_resp = client.get(path, headers=api_headers(c_allowed.id, team.email))
        assert ok_resp.status_code == 200, f"{path} failed for allowed client: {ok_resp.text}"

    for path in (
        f"/clients/{c_hidden.id}/setup",
        "/v2/watchlist",
        "/v2/watchlist/suggestions",
        "/v2/content/gaps",
        "/v2/optimizer",
    ):
        denied_resp = client.get(path, headers=api_headers(c_hidden.id, team.email))
        assert denied_resp.status_code == 403, f"{path} leaked for hidden client: {denied_resp.status_code}"


# ── Pair 11: Consulting Service Mode across Setup + Overview ──────────────────


def test_t3_pair_consulting_service_mode_setup_and_overview(client, db, tier, admin_user):
    c = make_client(
        db,
        tier,
        "Consulting Pair Co",
        status=ClientStatus.ONBOARDING,
        service_mode="consulting",
    )

    setup_res = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c))
    assert setup_res.status_code == 200
    setup = setup_res.json()
    assert setup["service_mode"] == "consulting"
    keys = [s["key"] for s in setup["steps"]]
    assert "consulting_profile" in keys
    assert "consulting_deliverable" in keys
    assert "first_run" not in keys

    overview_res = client.get("/v2/clients/overview", headers=admin_headers(c))
    assert overview_res.status_code == 200
    row = next(item for item in overview_res.json()["clients"] if item["id"] == str(c.id))
    assert row["service_mode"] == "consulting"
    assert row["plan_label"] == "Consulting"
    assert row["impressions"] is None
    assert row["total_sessions"] is None
    assert row["leads"] is None


# ── Pair 12: Watchlist Bucket DELETE + Setup Checklist Reassessment ────────────


def test_t3_pair_watchlist_bucket_delete_and_setup_reassessment(client, db, tier, admin_user):
    c = make_client(db, tier, "Bucket Delete Setup Co")
    bucket = seed_bucket(db, c, "Temp Bucket")
    seed_kw(db, bucket, c, "temp keyword one")
    seed_kw(db, bucket, c, "temp keyword two")
    db.commit()

    before = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c)).json()
    assert _step_map(before)["watchlist"]["done"] is True

    unconfirmed = client.delete(f"/v2/watchlist/buckets/{bucket.id}", headers=admin_headers(c))
    assert unconfirmed.status_code == 409

    still_done = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c)).json()
    assert _step_map(still_done)["watchlist"]["done"] is True

    confirmed = client.delete(
        f"/v2/watchlist/buckets/{bucket.id}",
        headers=admin_headers(c),
        params={"confirm": "true"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["deleted"] is True
    assert confirmed.json()["deleted_keywords"] == 2

    after = client.get(f"/clients/{c.id}/setup", headers=admin_headers(c)).json()
    assert _step_map(after)["watchlist"]["done"] is False
    assert after["done"] == before["done"] - 1


# ── Pair 13: Baseline Lock Sync Conversions + Overview Leads Recalculation ────


def test_t3_pair_baseline_lock_sync_conversions_and_overview(client, db, tier, admin_user):
    c = make_client(db, tier, "Baseline Sync Overview Co", business_model="lead_gen")
    seed_ga4_baseline_window(
        db,
        c,
        months=7,
        end_month_day=_shift_month(date.today().replace(day=1), -2),
        leads_per_month=10,
        event_name="generate_lead",
    )
    recent = date.today() - timedelta(days=3)
    seed_ga4_traffic(db, c, recent, 400, channel=OrganicChannel.ORGANIC_SEARCH, url="/")
    seed_ga4_event(db, c, recent, "generate_lead", 8, url="/")
    seed_ga4_event(db, c, recent, "quote_submit", 5, url="/quote")
    db.commit()

    # Before sync: only generate_lead is active -> overview leads == 8
    ov_before = client.get("/v2/clients/overview", headers=admin_headers(c)).json()
    row_before = next(item for item in ov_before["clients"] if item["id"] == str(c.id))
    assert row_before["leads"] == 8

    # Lock baseline syncing both lead_events
    lock_res = client.post(
        f"/clients/{c.id}/baseline/lock",
        headers=admin_headers(c),
        json={
            "source": "ga4",
            "months": 24,
            "lead_events": ["generate_lead", "quote_submit"],
            "sync_lead_conversions": True,
        },
    )
    assert lock_res.status_code == 200, lock_res.text
    assert lock_res.json()["lead_conversions_changed"] is not None

    ov_after = client.get("/v2/clients/overview", headers=admin_headers(c)).json()
    row_after = next(item for item in ov_after["clients"] if item["id"] == str(c.id))
    assert row_after["leads"] == 13


# ── Pair 14: Watchlist Bulk Add + GSC Suggestions Search Filter ───────────────


def test_t3_pair_watchlist_bulk_add_and_suggestions_filter(client, db, tier, admin_user):
    c = make_client(db, tier, "Bulk Suggestions Pair Co", brand_aliases=["bulk suggestions"])
    set_integration(db, c, IntegrationProvider.GSC, "sc-domain:bulksugg.example")
    recent = date.today() - timedelta(days=2)
    seed_indexable_site(db, c, count=10, snap_date=recent)
    seed_gsc_query_page(db, c, recent, "sewer hydro jetting cost", 480, 7.5, clicks=18, url="/services/item-1")
    seed_gsc_query_page(db, c, recent, "sewer camera inspection", 410, 9.2, clicks=14, url="/services/item-2")
    seed_gsc_query_page(db, c, recent, "water softener installation", 350, 11.0, clicks=10, url="/services/item-3")
    db.commit()

    sewer_sugg = client.get(
        "/v2/watchlist/suggestions",
        headers=admin_headers(c),
        params={"search": "sewer"},
    )
    assert sewer_sugg.status_code == 200
    sewer_keys = {s["key"] for s in sewer_sugg.json()["suggestions"]}
    assert sewer_keys == {"sewer hydro jetting cost", "sewer camera inspection"}

    bulk = client.post(
        "/v2/watchlist/keywords/bulk",
        headers=admin_headers(c),
        json={
            "items": [
                {"keyword": "sewer hydro jetting cost", "bucket_name": "Sewer Services"},
                {"keyword": "sewer camera inspection", "bucket_name": "Sewer Services"},
            ]
        },
    )
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()["created_count"] == 2

    remaining_sewer = client.get(
        "/v2/watchlist/suggestions",
        headers=admin_headers(c),
        params={"search": "sewer"},
    ).json()
    assert remaining_sewer["suggestions"] == []

    all_remaining = client.get("/v2/watchlist/suggestions", headers=admin_headers(c)).json()
    assert "water softener installation" in {s["key"] for s in all_remaining["suggestions"]}
