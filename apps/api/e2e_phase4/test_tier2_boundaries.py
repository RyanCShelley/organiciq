"""Tier 2 E2E Tests: Boundary, Corner-Case, Empty/Null, Validation & RBAC Negative cases for Phase 4."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.core.settings import get_settings
from app.models.baseline import BaselineVersion
from app.models.client import ClientStatus
from app.models.config import OrganicChannel
from app.models.integration import ConnectionStatus, IntegrationProvider
from app.models.schema_tools import ContentModelRun
from app.models.user import UserRole
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from e2e_phase4.conftest import (
    admin_headers,
    api_headers,
    make_client,
    make_user,
    seed_bucket,
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


# ── F1/F2: Guided Setup Boundaries & RBAC (6 tests) ──────────────────────────


def test_f1_t2_client_viewer_forbidden_on_setup(client, db, client_a):
    viewer = make_user(
        db,
        email="viewer-setup@clienta.example",
        role=UserRole.CLIENT_VIEWER,
        assign_clients=[client_a],
    )
    resp = client.get(
        f"/clients/{client_a.id}/setup",
        headers=api_headers(client_a.id, viewer.email),
    )
    assert resp.status_code == 403


def test_f1_t2_unassigned_sma_team_forbidden_on_setup(client, db, client_a, client_b):
    staff = make_user(
        db,
        email="staff-setup@smamarketing.com",
        role=UserRole.SMA_TEAM,
        assign_clients=[client_a],
    )
    resp = client.get(
        f"/clients/{client_b.id}/setup",
        headers=api_headers(client_b.id, staff.email),
    )
    assert resp.status_code == 403


def test_f1_t2_unknown_client_uuid_returns_404_on_setup(client, admin_user):
    resp = client.get(
        f"/clients/{uuid.uuid4()}/setup",
        headers=api_headers(email=admin_user.email),
    )
    assert resp.status_code == 404


def test_f1_t2_brand_new_client_zero_integrations_blocks_downstream_steps(
    client, db, tier, admin_user
):
    fresh = make_client(db, tier, "Brand New Setup Co", status=ClientStatus.ONBOARDING)
    resp = client.get(
        f"/clients/{fresh.id}/setup",
        headers=api_headers(fresh.id, admin_user.email),
    )
    assert resp.status_code == 200
    body = resp.json()
    steps = {s["key"]: s for s in body["steps"]}

    assert "content_sources" not in steps
    assert "conversion_pages" not in steps
    assert steps["account"]["done"] is True
    assert steps["sources"]["done"] is False
    for blocked_key in ("pull", "leads", "baseline", "first_run"):
        assert steps[blocked_key]["done"] is False
        assert steps[blocked_key]["blocked_by"]
    assert body["next"] == "sources"
    assert body["done"] == 1
    assert steps["competitors"]["optional"] is True


def test_f1_t2_execution_requires_tier_id_while_consulting_allows_omitted_tier_id(
    client, admin_user
):
    hdr = api_headers(email=admin_user.email)
    exec_resp = client.post(
        "/clients",
        json={
            "client_name": "Exec Missing Tier",
            "domain": "exec-missing-tier.example",
            "service_mode": "execution",
        },
        headers=hdr,
    )
    assert exec_resp.status_code == 422

    cons_resp = client.post(
        "/clients",
        json={
            "client_name": "Consulting No Tier",
            "domain": "consulting-no-tier.example",
            "service_mode": "consulting",
        },
        headers=hdr,
    )
    assert cons_resp.status_code == 201, cons_resp.text
    cons_body = cons_resp.json()
    assert cons_body["service_mode"] == "consulting"
    assert cons_body["plan_label"] == "Consulting"
    assert cons_body["tier_id"] is not None


def test_f1_t2_optional_competitors_never_blocks_or_inflates_required_setup_total(
    client, db, tier, admin_user
):
    ready = make_client(db, tier, "Ready Core Co", competitor_domains=[])
    set_integration(db, ready, IntegrationProvider.GA4, "properties/1111")
    set_integration(db, ready, IntegrationProvider.GSC, "sc-domain:readycore.example")
    seed_ga4_baseline_window(db, ready, months=7)
    seed_gsc_page(db, ready, date.today() - timedelta(days=2), "/", 100, 10)
    db.commit()

    lock_resp = client.post(
        f"/clients/{ready.id}/baseline/lock",
        json={"source": "ga4"},
        headers=admin_headers(ready),
    )
    assert lock_resp.status_code == 200, lock_resp.text

    bucket = seed_bucket(db, ready, "Core")
    seed_kw(db, bucket, ready, "ready core keyword")
    seed_setup_completion_extras(db, ready)
    db.commit()

    resp = client.get(
        f"/clients/{ready.id}/setup",
        headers=api_headers(ready.id, admin_user.email),
    )
    assert resp.status_code == 200
    body = resp.json()
    steps = {s["key"]: s for s in body["steps"]}
    assert steps["competitors"]["optional"] is True
    assert steps["competitors"]["done"] is False
    assert body["done"] == body["total"]
    assert body["next"] is None


# ── F3: Baseline & Projections Boundaries & RBAC (6 tests) ───────────────────


def test_f3_t2_baseline_series_missing_ga4_or_lead_definition_returns_400(
    client, db, client_a
):
    headers = admin_headers(client_a)
    r_no_def = client.get(f"/clients/{client_a.id}/baseline/series", headers=headers)
    assert r_no_def.status_code == 400
    assert "lead" in r_no_def.json()["detail"].lower()

    seed_conversion_def(db, client_a, event_name="generate_lead", active=True)
    db.commit()
    r_no_ga4 = client.get(f"/clients/{client_a.id}/baseline/series", headers=headers)
    assert r_no_ga4.status_code == 400
    assert "ga4" in r_no_ga4.json()["detail"].lower()


def test_f3_t2_baseline_series_partial_only_month_returns_400(client, db, client_a):
    seed_conversion_def(db, client_a, event_name="generate_lead", active=True)
    month_start = date(2026, 10, 1)
    mid_month = date(2026, 10, 15)
    seed_ga4_traffic(db, client_a, month_start, 500, channel=OrganicChannel.ORGANIC_SEARCH)
    seed_ga4_event(db, client_a, month_start, "generate_lead", 10)
    seed_watermark(db, client_a, "ga4", mid_month)
    db.commit()

    resp = client.get(
        f"/clients/{client_a.id}/baseline/series",
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 400
    assert "complete month" in resp.json()["detail"].lower()


def test_f3_t2_low_lead_volume_emits_warning_without_blocking_lock(client, db, client_a):
    seed_ga4_baseline_window(
        db,
        client_a,
        months=7,
        sessions_per_month=1000,
        direct_sessions_per_month=200,
        leads_per_month=2,  # 14 total leads (< 30)
    )
    headers = admin_headers(client_a)

    series_resp = client.get(f"/clients/{client_a.id}/baseline/series", headers=headers)
    assert series_resp.status_code == 200, series_resp.text
    series_body = series_resp.json()
    low_vol_flags = [f for f in series_body["flags"] if f["code"] == "low_volume"]
    assert len(low_vol_flags) == 1
    assert low_vol_flags[0]["level"] == "warning"
    assert series_body["can_lock"] is True

    lock_resp = client.post(
        f"/clients/{client_a.id}/baseline/lock",
        json={"source": "ga4"},
        headers=headers,
    )
    assert lock_resp.status_code == 200, lock_resp.text
    assert lock_resp.json()["version"]["version"] == 1


def test_f3_t2_relock_v2_rejects_short_note_or_missing_reason_code(client, db, client_a):
    seed_ga4_baseline_window(db, client_a, months=7, leads_per_month=10)
    headers = admin_headers(client_a)

    v1 = client.post(
        f"/clients/{client_a.id}/baseline/lock",
        json={"source": "ga4"},
        headers=headers,
    )
    assert v1.status_code == 200

    no_reason = client.post(
        f"/clients/{client_a.id}/baseline/lock",
        json={"source": "ga4", "reason_note": "A valid length note for rebaseline"},
        headers=headers,
    )
    assert no_reason.status_code == 400
    assert "reason" in no_reason.json()["detail"].lower()

    bad_reason = client.post(
        f"/clients/{client_a.id}/baseline/lock",
        json={
            "source": "ga4",
            "reason_code": "unknown_reason",
            "reason_note": "A valid length note for rebaseline",
        },
        headers=headers,
    )
    assert bad_reason.status_code == 400
    assert "reason" in bad_reason.json()["detail"].lower()

    short_note = client.post(
        f"/clients/{client_a.id}/baseline/lock",
        json={
            "source": "ga4",
            "reason_code": "relaunch",
            "reason_note": "too short",
        },
        headers=headers,
    )
    assert short_note.status_code == 400
    assert "character" in short_note.json()["detail"].lower()

    assert db.query(BaselineVersion).filter(BaselineVersion.client_id == client_a.id).count() == 1

    valid_v2 = client.post(
        f"/clients/{client_a.id}/baseline/lock",
        json={
            "source": "ga4",
            "reason_code": "relaunch",
            "reason_note": "Site relaunched with clean tracking.",
        },
        headers=headers,
    )
    assert valid_v2.status_code == 200
    assert valid_v2.json()["version"]["version"] == 2


def test_f3_t2_negative_monthly_lead_goal_rejected_422_and_zero_boundary(client, db, client_a):
    seed_ga4_baseline_window(db, client_a, months=7, leads_per_month=10)
    headers = admin_headers(client_a)

    neg_goal = client.post(
        f"/clients/{client_a.id}/baseline/goal",
        json={"monthly_lead_goal": -1},
        headers=headers,
    )
    assert neg_goal.status_code == 422

    neg_lock = client.post(
        f"/clients/{client_a.id}/baseline/lock",
        json={"source": "ga4", "monthly_lead_goal": -10},
        headers=headers,
    )
    assert neg_lock.status_code == 422

    zero_goal = client.post(
        f"/clients/{client_a.id}/baseline/goal",
        json={"monthly_lead_goal": 0},
        headers=headers,
    )
    assert zero_goal.status_code == 200
    assert zero_goal.json()["current"] == 0


def test_f3_t2_client_viewer_forbidden_on_baseline_endpoints(client, db, client_a):
    seed_ga4_baseline_window(db, client_a, months=7, leads_per_month=10)
    viewer = make_user(
        db,
        email="viewer-baseline@clienta.example",
        role=UserRole.CLIENT_VIEWER,
        assign_clients=[client_a],
    )
    hdr = api_headers(client_a.id, viewer.email)

    assert client.get(f"/clients/{client_a.id}/baseline/series", headers=hdr).status_code == 403
    assert client.get(f"/clients/{client_a.id}/baseline/events", headers=hdr).status_code == 403
    assert client.get(f"/clients/{client_a.id}/baseline/pillars", headers=hdr).status_code == 403
    assert client.get(f"/clients/{client_a.id}/baseline/versions", headers=hdr).status_code == 403
    assert (
        client.post(
            f"/clients/{client_a.id}/baseline/goal",
            json={"monthly_lead_goal": 25},
            headers=hdr,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/clients/{client_a.id}/baseline/lock",
            json={"source": "ga4"},
            headers=hdr,
        ).status_code
        == 403
    )


# ── F4: Watchlist CRUD Boundaries & RBAC (7 tests) ───────────────────────────


def test_f4_t2_patch_keyword_normalized_collision_returns_409(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Core")
    kw1 = seed_kw(db, bucket, client_a, "Emergency Plumber")
    kw2 = seed_kw(db, bucket, client_a, "Drain Cleaning")
    db.commit()

    resp = client.patch(
        f"/v2/watchlist/keywords/{kw2.id}",
        json={"keyword": "  emergency   PLUMBER  "},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 409

    db.expire_all()
    assert db.get(WatchlistKeyword, kw1.id).keyword == "Emergency Plumber"
    assert db.get(WatchlistKeyword, kw2.id).keyword == "Drain Cleaning"


def test_f4_t2_create_and_patch_bucket_normalized_collision_returns_409(client, db, client_a):
    b1 = seed_bucket(db, client_a, "Local Services")
    b2 = seed_bucket(db, client_a, "Commercial")
    db.commit()

    dup_post = client.post(
        "/v2/watchlist/buckets",
        json={"name": "  local   SERVICES "},
        headers=admin_headers(client_a),
    )
    assert dup_post.status_code == 409

    dup_patch = client.patch(
        f"/v2/watchlist/buckets/{b2.id}",
        json={"name": "LOCAL services"},
        headers=admin_headers(client_a),
    )
    assert dup_patch.status_code == 409

    db.expire_all()
    assert db.get(WatchlistBucket, b1.id).name == "Local Services"
    assert db.get(WatchlistBucket, b2.id).name == "Commercial"


def test_f4_t2_cross_client_patch_and_delete_keyword_or_bucket_returns_404(
    client, db, client_a, client_b
):
    bucket_a = seed_bucket(db, client_a, "Client A Bucket")
    kw_a = seed_kw(db, bucket_a, client_a, "client a private term")
    db.commit()

    headers_b = admin_headers(client_b)
    assert (
        client.patch(
            f"/v2/watchlist/keywords/{kw_a.id}",
            json={"notes": "tamper"},
            headers=headers_b,
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/v2/watchlist/keywords/{kw_a.id}", headers=headers_b).status_code == 404
    )
    assert (
        client.patch(
            f"/v2/watchlist/buckets/{bucket_a.id}",
            json={"name": "Hijacked"},
            headers=headers_b,
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/v2/watchlist/buckets/{bucket_a.id}",
            params={"confirm": True},
            headers=headers_b,
        ).status_code
        == 404
    )

    db.expire_all()
    assert db.get(WatchlistKeyword, kw_a.id) is not None
    assert db.get(WatchlistBucket, bucket_a.id) is not None


def test_f4_t2_nonexistent_keyword_and_bucket_uuid_returns_404(client, client_a):
    headers = admin_headers(client_a)
    missing_kw = uuid.uuid4()
    missing_bucket = uuid.uuid4()

    assert (
        client.patch(
            f"/v2/watchlist/keywords/{missing_kw}",
            json={"volume": 500},
            headers=headers,
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/v2/watchlist/keywords/{missing_kw}", headers=headers).status_code == 404
    )
    assert (
        client.patch(
            f"/v2/watchlist/buckets/{missing_bucket}",
            json={"name": "Nope"},
            headers=headers,
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/v2/watchlist/buckets/{missing_bucket}", headers=headers).status_code
        == 404
    )


def test_f4_t2_blank_or_whitespace_keyword_and_bucket_name_returns_422(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Valid Bucket")
    kw = seed_kw(db, bucket, client_a, "valid term")
    db.commit()
    headers = admin_headers(client_a)

    for blank in ("", "   \t\n  "):
        assert (
            client.post("/v2/watchlist/keywords", json={"keyword": blank}, headers=headers)
            .status_code
            == 422
        )
        assert (
            client.patch(
                f"/v2/watchlist/keywords/{kw.id}", json={"keyword": blank}, headers=headers
            ).status_code
            == 422
        )
        assert (
            client.post("/v2/watchlist/buckets", json={"name": blank}, headers=headers).status_code
            == 422
        )
        assert (
            client.patch(
                f"/v2/watchlist/buckets/{bucket.id}", json={"name": blank}, headers=headers
            ).status_code
            == 422
        )


def test_f4_t2_delete_nonempty_bucket_requires_confirm_true_409_then_200(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Non-Empty")
    seed_kw(db, bucket, client_a, "term one")
    seed_kw(db, bucket, client_a, "term two")
    db.commit()
    headers = admin_headers(client_a)

    refused = client.delete(f"/v2/watchlist/buckets/{bucket.id}", headers=headers)
    assert refused.status_code == 409

    confirmed = client.delete(
        f"/v2/watchlist/buckets/{bucket.id}",
        params={"confirm": True},
        headers=headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["deleted"] is True
    assert confirmed.json()["deleted_keywords"] == 2


def test_f4_t2_client_viewer_forbidden_on_all_watchlist_endpoints(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Core")
    kw = seed_kw(db, bucket, client_a, "slab leak")
    viewer = make_user(
        db,
        email="viewer-wl@clienta.example",
        role=UserRole.CLIENT_VIEWER,
        assign_clients=[client_a],
    )
    db.commit()
    hdr = api_headers(client_a.id, viewer.email)

    assert client.get("/v2/watchlist", headers=hdr).status_code == 403
    assert client.get("/v2/watchlist/suggestions", headers=hdr).status_code == 403
    assert (
        client.post("/v2/watchlist/keywords", json={"keyword": "new kw"}, headers=hdr).status_code
        == 403
    )
    assert (
        client.post(
            "/v2/watchlist/keywords/bulk",
            json={"items": [{"keyword": "bulk kw"}]},
            headers=hdr,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/v2/watchlist/keywords/{kw.id}", json={"volume": 100}, headers=hdr
        ).status_code
        == 403
    )
    assert client.delete(f"/v2/watchlist/keywords/{kw.id}", headers=hdr).status_code == 403
    assert (
        client.post("/v2/watchlist/buckets", json={"name": "New Bucket"}, headers=hdr).status_code
        == 403
    )
    assert (
        client.patch(
            f"/v2/watchlist/buckets/{bucket.id}", json={"name": "Renamed"}, headers=hdr
        ).status_code
        == 403
    )
    assert client.delete(f"/v2/watchlist/buckets/{bucket.id}", headers=hdr).status_code == 403
    assert (
        client.post(
            "/v2/watchlist/import",
            json={"csv_text": "Topic,Keyword\nCore,new kw\n", "dry_run": True},
            headers=hdr,
        ).status_code
        == 403
    )


# ── F5: Watchlist GSC Suggestions Boundaries & RBAC (6 tests) ────────────────


def test_f5_t2_disconnected_gsc_returns_200_empty_suggestions(client, client_a):
    resp = client.get("/v2/watchlist/suggestions", headers=admin_headers(client_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["gsc_connected"] is False
    assert body["has_gsc_data"] is False
    assert body["google_through"] is None
    assert body["suggestions"] == []


def test_f5_t2_connected_gsc_zero_rows_returns_200_empty_suggestions(client, db, client_a):
    set_integration(
        db,
        client_a,
        IntegrationProvider.GSC,
        "sc-domain:clienta.example",
        ConnectionStatus.CONNECTED,
    )
    resp = client.get("/v2/watchlist/suggestions", headers=admin_headers(client_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["gsc_connected"] is True
    assert body["has_gsc_data"] is False
    assert body["google_through"] is None
    assert body["suggestions"] == []


def test_f5_t2_suggestions_limit_bounds_and_validation(client, db, client_a):
    set_integration(
        db,
        client_a,
        IntegrationProvider.GSC,
        "sc-domain:clienta.example",
        ConnectionStatus.CONNECTED,
    )
    today = date.today()
    for i in range(1, 5):
        seed_gsc_query_page(
            db,
            client_a,
            today - timedelta(days=5),
            f"commercial drain jetting option {i}",
            impressions=250 + i * 20,
            position=8.0,
            clicks=12,
        )
    db.commit()
    headers = admin_headers(client_a)

    lim1 = client.get("/v2/watchlist/suggestions", params={"limit": 1}, headers=headers)
    assert lim1.status_code == 200
    assert len(lim1.json()["suggestions"]) == 1

    lim100 = client.get("/v2/watchlist/suggestions", params={"limit": 100}, headers=headers)
    assert lim100.status_code == 200
    assert len(lim100.json()["suggestions"]) == 4

    assert (
        client.get("/v2/watchlist/suggestions", params={"limit": 0}, headers=headers).status_code
        == 422
    )
    assert (
        client.get("/v2/watchlist/suggestions", params={"limit": 101}, headers=headers).status_code
        == 422
    )


def test_f5_t2_suggestions_unmatched_search_returns_empty_list(client, db, client_a):
    set_integration(
        db,
        client_a,
        IntegrationProvider.GSC,
        "sc-domain:clienta.example",
        ConnectionStatus.CONNECTED,
    )
    seed_gsc_query_page(
        db,
        client_a,
        date.today() - timedelta(days=5),
        "hydro jetting sewer line",
        impressions=300,
        position=7.0,
        clicks=15,
    )
    db.commit()

    resp = client.get(
        "/v2/watchlist/suggestions",
        params={"search": "zzznomatch999"},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_gsc_data"] is True
    assert body["suggestions"] == []


def test_f5_t2_suggestions_rbac_client_viewer_and_unassigned_sma_team_403(
    client, db, client_a, client_b
):
    viewer = make_user(
        db,
        email="viewer-sug@clienta.example",
        role=UserRole.CLIENT_VIEWER,
        assign_clients=[client_a],
    )
    staff = make_user(
        db,
        email="staff-sug@smamarketing.com",
        role=UserRole.SMA_TEAM,
        assign_clients=[client_a],
    )
    assert (
        client.get(
            "/v2/watchlist/suggestions", headers=api_headers(client_a.id, viewer.email)
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/v2/watchlist/suggestions", headers=api_headers(client_b.id, staff.email)
        ).status_code
        == 403
    )


def test_f5_t2_suggestions_excludes_already_tracked_case_whitespace_variants(
    client, db, client_a
):
    set_integration(
        db,
        client_a,
        IntegrationProvider.GSC,
        "sc-domain:clienta.example",
        ConnectionStatus.CONNECTED,
    )
    bucket = seed_bucket(db, client_a, "Plumbing")
    seed_kw(db, bucket, client_a, "Trenchless  Sewer  Repair")
    today = date.today()
    seed_gsc_query_page(
        db,
        client_a,
        today - timedelta(days=3),
        "  TRENCHLESS sewer repair ",
        impressions=500,
        position=6.0,
        clicks=25,
    )
    seed_gsc_query_page(
        db,
        client_a,
        today - timedelta(days=3),
        "copper pipe repiping",
        impressions=400,
        position=9.0,
        clicks=15,
    )
    db.commit()

    resp = client.get(
        "/v2/watchlist/suggestions",
        params={"search": "repair"},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    keys = [s["key"] for s in resp.json()["suggestions"]]
    assert "trenchless sewer repair" not in keys


# ── F6: Watchlist Import & Scoping Boundaries & RBAC (6 tests) ───────────────


def test_f6_t2_import_empty_header_only_and_malformed_csv_no_500(client, db, client_a):
    headers = admin_headers(client_a)

    r_empty = client.post(
        "/v2/watchlist/import",
        json={"csv_text": "", "dry_run": False},
        headers=headers,
    )
    assert r_empty.status_code == 400

    r_bad_cols = client.post(
        "/v2/watchlist/import",
        json={"csv_text": "foo,bar\n1,2\n", "dry_run": False},
        headers=headers,
    )
    assert r_bad_cols.status_code == 400

    r_header_only = client.post(
        "/v2/watchlist/import",
        json={"csv_text": "Topic,Keyword\n", "dry_run": False},
        headers=headers,
    )
    assert r_header_only.status_code == 200
    body = r_header_only.json()
    assert body["rows_read"] == 0
    assert body["keywords_created"] == 0
    assert db.query(WatchlistKeyword).filter(WatchlistKeyword.client_id == client_a.id).count() == 0


def test_f6_t2_import_dry_run_previews_without_persisting_to_db(client, db, client_a):
    headers = admin_headers(client_a)
    csv_text = "Topic,Keyword,Volume,Difficulty\nCore,emergency pipe repair,400,25\nCore,slab leak repair,300,30\n"

    dry = client.post(
        "/v2/watchlist/import",
        json={"csv_text": csv_text, "dry_run": True},
        headers=headers,
    )
    assert dry.status_code == 200
    dry_body = dry.json()
    assert dry_body["dry_run"] is True
    assert dry_body["buckets_created"] == 1
    assert dry_body["keywords_created"] == 2

    wl = client.get("/v2/watchlist", headers=headers).json()
    assert wl["keyword_count"] == 0
    assert wl["buckets"] == []
    assert db.query(WatchlistBucket).filter(WatchlistBucket.client_id == client_a.id).count() == 0


def test_f6_t2_oversized_keyword_over_400_chars_rejected_422(client, db, client_a):
    bucket = seed_bucket(db, client_a, "Core")
    kw = seed_kw(db, bucket, client_a, "normal keyword")
    db.commit()
    headers = admin_headers(client_a)
    too_long = "k" * 401

    assert (
        client.post(
            "/v2/watchlist/keywords", json={"keyword": too_long}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v2/watchlist/keywords/bulk",
            json={"items": [{"keyword": too_long}]},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/v2/watchlist/keywords/{kw.id}", json={"keyword": too_long}, headers=headers
        ).status_code
        == 422
    )


def test_f6_t2_delete_nonexistent_bucket_returns_404(client, client_a):
    resp = client.delete(
        f"/v2/watchlist/buckets/{uuid.uuid4()}",
        params={"confirm": True},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 404


def test_f6_t2_unassigned_sma_team_forbidden_on_watchlist_mutations(
    client, db, client_a, client_b
):
    bucket_b = seed_bucket(db, client_b, "Client B Bucket")
    kw_b = seed_kw(db, bucket_b, client_b, "client b kw")
    staff = make_user(
        db,
        email="staff-wl@smamarketing.com",
        role=UserRole.SMA_TEAM,
        assign_clients=[client_a],
    )
    db.commit()
    hdr = api_headers(client_b.id, staff.email)

    assert (
        client.post("/v2/watchlist/keywords", json={"keyword": "x"}, headers=hdr).status_code
        == 403
    )
    assert (
        client.patch(
            f"/v2/watchlist/keywords/{kw_b.id}", json={"notes": "x"}, headers=hdr
        ).status_code
        == 403
    )
    assert client.delete(f"/v2/watchlist/keywords/{kw_b.id}", headers=hdr).status_code == 403
    assert (
        client.post("/v2/watchlist/buckets", json={"name": "New"}, headers=hdr).status_code == 403
    )
    assert (
        client.patch(
            f"/v2/watchlist/buckets/{bucket_b.id}", json={"name": "Renamed"}, headers=hdr
        ).status_code
        == 403
    )
    assert client.delete(f"/v2/watchlist/buckets/{bucket_b.id}", headers=hdr).status_code == 403
    assert (
        client.post(
            "/v2/watchlist/import",
            json={"csv_text": "Topic,Keyword\nA,b\n", "dry_run": False},
            headers=hdr,
        ).status_code
        == 403
    )


def test_f6_t2_import_records_skipped_missing_topic_and_bad_numeric_warnings(client, client_a):
    csv_text = (
        "Topic,Keyword,Volume,Difficulty\n"
        ",orphan keyword,100,20\n"
        "Core,,100,20\n"
        "Core,valid keyword,notanumber,150\n"
    )
    resp = client.post(
        "/v2/watchlist/import",
        json={"csv_text": csv_text, "dry_run": False},
        headers=admin_headers(client_a),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["skipped"]) == 2
    assert len(body["warnings"]) == 2
    assert body["keywords_created"] == 1


# ── F7: Content Gaps Filtering Boundaries & RBAC (7 tests) ───────────────────


def test_f7_t2_under_10_indexable_pages_returns_blocked_empty_gaps(client, db, client_a):
    snap = date.today()
    root = f"https://{client_a.domain}"
    for i in range(9):
        seed_crawl_page(
            db,
            client_a,
            root,
            f"/page-{i}",
            snap,
            title=f"Page {i}",
            indexable=True,
        )
    # Add non-indexable pages that must NOT count toward the 10-page threshold
    for i in range(3):
        seed_crawl_page(
            db,
            client_a,
            root,
            f"/noindex-{i}",
            snap,
            title=f"Noindex {i}",
            indexable=False,
        )
    db.commit()

    resp = client.get("/v2/content/gaps", headers=admin_headers(client_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["blocked"]
    assert "9 indexable" in body["blocked"]
    assert body["gaps"] == []


def test_f7_t2_zero_gsc_and_zero_serp_returns_empty_gaps_cleanly(client, db, client_a):
    seed_indexable_site(db, client_a, count=12)

    resp = client.get("/v2/content/gaps", headers=admin_headers(client_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["blocked"] is None
    assert body["gaps"] == []
    assert body["gaps_total"] == 0


def _seed_two_relevant_gaps(db, client_obj) -> tuple[str, str]:
    """Seed >=10 indexable pages + topical vocabulary + two priced GSC demand gaps."""
    today = date.today()
    seed_indexable_site(db, client_obj, count=12)
    root = f"https://{client_obj.domain}"
    seed_crawl_page(
        db,
        client_obj,
        root,
        "/services/drain-cleaning",
        today,
        title="Drain Cleaning Services",
        sections=[
            {
                "level": 1,
                "heading": "Drain Cleaning",
                "first_paragraph": "Residential and commercial drain maintenance and inspection.",
            }
        ],
    )
    term_one = "emergency drain jetting"
    term_two = "commercial drain descaling"
    for term in (term_one, term_two):
        seed_gsc_query_page(
            db,
            client_obj,
            today - timedelta(days=5),
            term,
            impressions=600,
            position=25.0,
            clicks=8,
            url="/services/drain-cleaning",
        )
        seed_ser_metric(db, client_obj, term, volume=700, difficulty=20, data_found=True)
    db.commit()
    return term_one, term_two


def test_f7_t2_gaps_q_filter_matches_substring_and_returns_empty_unmatched(
    client, db, client_a
):
    term_one, term_two = _seed_two_relevant_gaps(db, client_a)
    headers = admin_headers(client_a)

    matched = client.get("/v2/content/gaps", params={"q": "jetting"}, headers=headers)
    assert matched.status_code == 200
    terms = [g["term"] for g in matched.json()["gaps"]]
    assert terms == [term_one]
    assert term_two not in terms

    unmatched = client.get("/v2/content/gaps", params={"q": "zzznomatch999"}, headers=headers)
    assert unmatched.status_code == 200
    assert unmatched.json()["gaps"] == []
    assert unmatched.json()["gaps_total"] == 0


def test_f7_t2_ignore_and_restore_content_gap_toggles_visibility(client, db, client_a):
    term_one, term_two = _seed_two_relevant_gaps(db, client_a)
    headers = admin_headers(client_a)

    assert (
        client.post(
            "/v2/content/ignore",
            json={"area": "gap", "key": term_one},
            headers=headers,
        ).status_code
        == 200
    )

    live = client.get("/v2/content/gaps", params={"ignored": False}, headers=headers).json()
    live_terms = {g["term"] for g in live["gaps"]}
    assert term_one not in live_terms
    assert term_two in live_terms
    assert live["ignored_total"] == 1

    ignored_view = client.get("/v2/content/gaps", params={"ignored": True}, headers=headers).json()
    ignored_terms = [g["term"] for g in ignored_view["gaps"]]
    assert ignored_terms == [term_one]
    assert ignored_view["gaps"][0]["ignored"] is True

    assert (
        client.post(
            "/v2/content/restore",
            json={"area": "gap", "key": term_one},
            headers=headers,
        ).status_code
        == 200
    )

    restored = client.get("/v2/content/gaps", params={"ignored": False}, headers=headers).json()
    assert {g["term"] for g in restored["gaps"]} == {term_one, term_two}
    assert restored["ignored_total"] == 0


def test_f7_t2_watch_target_excluded_suppresses_gap_across_case_and_whitespace(
    client, db, client_a
):
    term_one, term_two = _seed_two_relevant_gaps(db, client_a)
    seed_watch_target_excluded(db, client_a, f"  {term_one.upper().replace(' ', '   ')}  ")
    db.commit()

    resp = client.get("/v2/content/gaps", headers=admin_headers(client_a))
    assert resp.status_code == 200
    terms = {g["term"] for g in resp.json()["gaps"]}
    assert term_one not in terms
    assert term_two in terms


def test_f7_t2_client_viewer_forbidden_on_content_gaps_and_mutations(client, db, client_a):
    viewer = make_user(
        db,
        email="viewer-gaps@clienta.example",
        role=UserRole.CLIENT_VIEWER,
        assign_clients=[client_a],
    )
    hdr = api_headers(client_a.id, viewer.email)

    assert client.get("/v2/content/gaps", headers=hdr).status_code == 403
    assert (
        client.post("/v2/content/ignore", json={"area": "gap", "key": "x"}, headers=hdr).status_code
        == 403
    )
    assert (
        client.post("/v2/content/restore", json={"area": "gap", "key": "x"}, headers=hdr).status_code
        == 403
    )
    assert (
        client.post(
            "/v2/content/draft",
            json={"kind": "brief", "key": "x", "depth": "quick"},
            headers=hdr,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v2/content/calendar",
            json={"kind": "new_page", "title": "T", "target": "/t"},
            headers=hdr,
        ).status_code
        == 403
    )


def test_f7_t2_unassigned_sma_team_forbidden_on_content_gaps_and_ignore(
    client, db, client_a, client_b
):
    staff = make_user(
        db,
        email="staff-gaps@smamarketing.com",
        role=UserRole.SMA_TEAM,
        assign_clients=[client_a],
    )
    hdr = api_headers(client_b.id, staff.email)

    assert client.get("/v2/content/gaps", headers=hdr).status_code == 403
    assert (
        client.post("/v2/content/ignore", json={"area": "gap", "key": "x"}, headers=hdr).status_code
        == 403
    )
    assert (
        client.post("/v2/content/restore", json={"area": "gap", "key": "x"}, headers=hdr).status_code
        == 403
    )


# ── F8: Content Optimizer Ad-Hoc Keyword Boundaries & RBAC (6 tests) ─────────


def test_f8_t2_blank_whitespace_adhoc_keyword_on_zero_gsc_page_fails_cleanly(
    client, db, client_a, stub_optimizer_llm
):
    url = f"https://{client_a.domain}/zero-gsc-blank-kw"
    headers = admin_headers(client_a)

    resp = client.post(
        "/v2/optimizer/draft",
        json={"url": url, "kind": "opening", "depth": "quick", "keyword": "   \t\n  "},
        headers=headers,
    )
    assert resp.status_code == 202
    run_id = uuid.UUID(resp.json()["id"])

    db.expire_all()
    run_row = db.get(ContentModelRun, run_id)
    assert run_row is not None
    assert run_row.status == "failed"
    assert "no searches with enough data" in (run_row.error or "").lower()

    page = client.get("/v2/optimizer/page", params={"url": url}, headers=headers)
    assert page.status_code == 200
    assert page.json()["drafts"]["opening"]["status"] == "failed"


def test_f8_t2_overlong_adhoc_keyword_rejected_422(client, client_a, stub_optimizer_llm):
    url = f"https://{client_a.domain}/long-kw-page"
    headers = admin_headers(client_a)

    for length in (301, 401):
        resp = client.post(
            "/v2/optimizer/draft",
            json={"url": url, "kind": "opening", "depth": "quick", "keyword": "k" * length},
            headers=headers,
        )
        assert resp.status_code == 422


def test_f8_t2_missing_anthropic_api_key_returns_400(client, client_a, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    headers = admin_headers(client_a)

    queue = client.get("/v2/optimizer", headers=headers)
    assert queue.status_code == 200
    assert queue.json()["model_ready"] is False

    resp = client.post(
        "/v2/optimizer/draft",
        json={
            "url": f"https://{client_a.domain}/no-key-page",
            "kind": "opening",
            "depth": "quick",
            "keyword": "slab leak detection",
        },
        headers=headers,
    )
    assert resp.status_code == 400


def test_f8_t2_invalid_kind_or_depth_returns_422(client, client_a, stub_optimizer_llm):
    url = f"https://{client_a.domain}/bad-enum-page"
    headers = admin_headers(client_a)

    bad_kind = client.post(
        "/v2/optimizer/draft",
        json={"url": url, "kind": "headline", "depth": "quick", "keyword": "slab leak"},
        headers=headers,
    )
    assert bad_kind.status_code == 422

    bad_depth = client.post(
        "/v2/optimizer/draft",
        json={"url": url, "kind": "opening", "depth": "ultra", "keyword": "slab leak"},
        headers=headers,
    )
    assert bad_depth.status_code == 422


def test_f8_t2_client_viewer_forbidden_and_cross_client_page_isolated(
    client, db, client_a, client_b, stub_optimizer_llm
):
    url_a = f"https://{client_a.domain}/private-opt"
    pasted = "Private Leak Service\n\nOur licensed specialists inspect residential slabs using thermal imaging and acoustic sensors."
    draft_a = client.post(
        "/v2/optimizer/draft",
        json={
            "url": url_a,
            "kind": "opening",
            "depth": "quick",
            "text": pasted,
            "keyword": "acoustic slab leak",
        },
        headers=admin_headers(client_a),
    )
    assert draft_a.status_code == 202

    # client_b cannot see client_a's draft
    page_b = client.get(
        "/v2/optimizer/page",
        params={"url": url_a},
        headers=admin_headers(client_b),
    )
    assert page_b.status_code == 200
    assert page_b.json()["drafts"]["opening"] is None

    viewer = make_user(
        db,
        email="viewer-opt@clienta.example",
        role=UserRole.CLIENT_VIEWER,
        assign_clients=[client_a],
    )
    hdr_v = api_headers(client_a.id, viewer.email)
    assert client.get("/v2/optimizer", headers=hdr_v).status_code == 403
    assert client.get("/v2/optimizer/page", params={"url": url_a}, headers=hdr_v).status_code == 403
    assert (
        client.post(
            "/v2/optimizer/draft",
            json={"url": url_a, "kind": "opening", "depth": "quick", "keyword": "x"},
            headers=hdr_v,
        ).status_code
        == 403
    )


def test_f8_t2_unassigned_sma_team_forbidden_on_optimizer(
    client, db, client_a, client_b, stub_optimizer_llm
):
    staff = make_user(
        db,
        email="staff-opt@smamarketing.com",
        role=UserRole.SMA_TEAM,
        assign_clients=[client_a],
    )
    hdr = api_headers(client_b.id, staff.email)

    assert client.get("/v2/optimizer", headers=hdr).status_code == 403
    assert (
        client.get(
            "/v2/optimizer/page",
            params={"url": f"https://{client_b.domain}/x"},
            headers=hdr,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v2/optimizer/draft",
            json={
                "url": f"https://{client_b.domain}/x",
                "kind": "opening",
                "depth": "quick",
                "keyword": "x",
            },
            headers=hdr,
        ).status_code
        == 403
    )


# ── F9: Content Sources Cleanup Boundaries & RBAC (6 tests) ──────────────────


def test_f9_t2_v2_feeds_routes_return_404_even_for_sma_admin(client, client_a):
    headers = admin_headers(client_a)
    assert client.get("/v2/feeds", headers=headers).status_code == 404
    assert (
        client.post(
            "/v2/feeds",
            json={"url": "https://clienta.example/feed.xml", "label": "Blog"},
            headers=headers,
        ).status_code
        == 404
    )
    assert client.patch(f"/v2/feeds/{uuid.uuid4()}", json={"label": "X"}, headers=headers).status_code == 404
    assert client.delete(f"/v2/feeds/{uuid.uuid4()}", headers=headers).status_code == 404


def test_f9_t2_invalid_or_unsafe_sitemap_url_rejected_422(client, client_a, admin_user):
    headers = api_headers(email=admin_user.email)
    unsafe_urls = (
        "ftp://clienta.example/sitemap.xml",
        "http://localhost/sitemap.xml",
        "http://127.0.0.1/sitemap.xml",
        "http://169.254.169.254/latest/meta-data/",
        "https://user:pass@clienta.example/sitemap.xml",
        "http://internal-host/sitemap.xml",
    )
    for bad in unsafe_urls:
        resp = client.patch(
            f"/clients/{client_a.id}",
            json={"sitemap_url": bad},
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for {bad!r}, got {resp.status_code}"


def test_f9_t2_client_viewer_forbidden_on_patch_client(client, db, client_a):
    viewer = make_user(
        db,
        email="viewer-patch@clienta.example",
        role=UserRole.CLIENT_VIEWER,
        assign_clients=[client_a],
    )
    resp = client.patch(
        f"/clients/{client_a.id}",
        json={"sitemap_url": f"https://{client_a.domain}/sitemap.xml"},
        headers=api_headers(email=viewer.email),
    )
    assert resp.status_code == 403


def test_f9_t2_non_admin_sma_team_cannot_modify_admin_only_fields_on_patch_client(
    client, db, client_a
):
    staff = make_user(
        db,
        email="staff-patch@smamarketing.com",
        role=UserRole.SMA_TEAM,
        assign_clients=[client_a],
    )
    hdr = api_headers(email=staff.email)

    # Non-admin staff CAN update sitemap_url
    ok = client.patch(
        f"/clients/{client_a.id}",
        json={"sitemap_url": f"https://{client_a.domain}/sitemap.xml"},
        headers=hdr,
    )
    assert ok.status_code == 200

    # Non-admin staff CANNOT modify admin-only spend/allowance fields
    assert (
        client.patch(
            f"/clients/{client_a.id}",
            json={"crawl_page_limit": 9999},
            headers=hdr,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/clients/{client_a.id}",
            json={"custom_content_allowance": 99},
            headers=hdr,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/clients/{client_a.id}",
            json={"tier_id": str(uuid.uuid4())},
            headers=hdr,
        ).status_code
        == 403
    )


def test_f9_t2_patch_nonexistent_client_uuid_returns_404(client, admin_user):
    resp = client.patch(
        f"/clients/{uuid.uuid4()}",
        json={"sitemap_url": "https://example.com/sitemap.xml"},
        headers=api_headers(email=admin_user.email),
    )
    assert resp.status_code == 404


def test_f9_t2_unassigned_sma_team_forbidden_on_patch_client(client, db, client_a, client_b):
    staff = make_user(
        db,
        email="staff-cross@smamarketing.com",
        role=UserRole.SMA_TEAM,
        assign_clients=[client_a],
    )
    resp = client.patch(
        f"/clients/{client_b.id}",
        json={"sitemap_url": f"https://{client_b.domain}/sitemap.xml"},
        headers=api_headers(email=staff.email),
    )
    assert resp.status_code == 403


# ── F10/F11: All-Clients Overview Boundaries & RBAC (7 tests) ────────────────


def test_f10_t2_zero_gsc_ga4_events_client_returns_null_metrics_no_500(
    client, db, client_a, admin_user
):
    resp = client.get("/v2/clients/overview", headers=api_headers(email=admin_user.email))
    assert resp.status_code == 200
    items = {c["id"]: c for c in resp.json()["clients"]}
    row = items[str(client_a.id)]
    assert row["impressions"] is None
    assert row["clicks"] is None
    assert row["avg_position"] is None
    assert row["impressions_change_pct"] is None
    assert row["total_sessions"] is None
    assert row["organic_sessions"] is None
    assert row["organic_change_pct"] is None
    assert row["leads"] is None
    assert row["leads_change_pct"] is None
    assert row["gsc_through"] is None
    assert row["ga4_through"] is None


def test_f10_t2_sma_team_with_zero_assignments_gets_empty_clients_list(client, db, client_a):
    unassigned = make_user(
        db,
        email="lonely-team@smamarketing.com",
        role=UserRole.SMA_TEAM,
        assign_clients=[],
    )
    resp = client.get("/v2/clients/overview", headers=api_headers(email=unassigned.email))
    assert resp.status_code == 200
    body = resp.json()
    assert body["clients"] == []
    assert body["window"]["days"] == 30


def test_f10_t2_client_viewer_forbidden_on_overview(client, db, client_a):
    viewer = make_user(
        db,
        email="viewer-overview@clienta.example",
        role=UserRole.CLIENT_VIEWER,
        assign_clients=[client_a],
    )
    resp = client.get("/v2/clients/overview", headers=api_headers(email=viewer.email))
    assert resp.status_code == 403


def test_f10_t2_inactive_and_engagement_conversion_definitions_excluded_from_leads(
    client, db, client_a, client_b, admin_user
):
    as_of = date(2026, 10, 30)
    day = date(2026, 10, 20)

    # client_a: only inactive lead def + active engagement def -> leads must be None
    seed_ga4_traffic(db, client_a, day, 200, channel=OrganicChannel.ORGANIC_SEARCH)
    seed_conversion_def(db, client_a, event_name="old_lead", conversion_type="lead", active=False)
    seed_conversion_def(
        db, client_a, event_name="scroll_90", conversion_type="engagement", active=True
    )
    seed_ga4_event(db, client_a, day, "old_lead", 12)
    seed_ga4_event(db, client_a, day, "scroll_90", 40)

    # client_b: active lead def + inactive lead def + active engagement def -> only active lead counted
    seed_ga4_traffic(db, client_b, day, 300, channel=OrganicChannel.ORGANIC_SEARCH)
    seed_conversion_def(db, client_b, event_name="generate_lead", conversion_type="lead", active=True)
    seed_conversion_def(db, client_b, event_name="legacy_lead", conversion_type="lead", active=False)
    seed_conversion_def(
        db, client_b, event_name="video_play", conversion_type="engagement", active=True
    )
    seed_ga4_event(db, client_b, day, "generate_lead", 7)
    seed_ga4_event(db, client_b, day, "legacy_lead", 20)
    seed_ga4_event(db, client_b, day, "video_play", 99)
    db.commit()

    resp = client.get(
        "/v2/clients/overview",
        params={"as_of": as_of.isoformat()},
        headers=api_headers(email=admin_user.email),
    )
    assert resp.status_code == 200
    by_id = {c["id"]: c for c in resp.json()["clients"]}
    assert by_id[str(client_a.id)]["leads"] is None
    assert by_id[str(client_b.id)]["leads"] == 7


def test_f10_t2_lead_exclusion_date_window_and_url_pattern_wildcard_boundaries(
    client, db, client_a, admin_user
):
    as_of = date(2026, 10, 30)
    win_start = date(2026, 10, 10)
    win_end = date(2026, 10, 20)

    seed_conversion_def(db, client_a, event_name="generate_lead", conversion_type="lead", active=True)
    seed_ga4_traffic(db, client_a, date(2026, 10, 15), 500, channel=OrganicChannel.ORGANIC_SEARCH)
    seed_lead_exclusion(
        db,
        client_a,
        reason="QA form testing",
        url_pattern=f"https://{client_a.domain}/test-form*",
        date_from=win_start,
        date_to=win_end,
    )

    # Excluded: inside [date_from, date_to] (inclusive boundaries) AND matches /test-form*
    seed_ga4_event(db, client_a, win_start, "generate_lead", 4, url="/test-form")
    seed_ga4_event(db, client_a, win_end, "generate_lead", 6, url="/test-form/step-2")

    # Retained: outside date window even though URL matches /test-form*
    seed_ga4_event(db, client_a, date(2026, 10, 9), "generate_lead", 3, url="/test-form")
    seed_ga4_event(db, client_a, date(2026, 10, 21), "generate_lead", 5, url="/test-form/step-2")

    # Retained: inside date window but non-matching URL
    seed_ga4_event(db, client_a, date(2026, 10, 15), "generate_lead", 8, url="/contact")
    db.commit()

    resp = client.get(
        "/v2/clients/overview",
        params={"as_of": as_of.isoformat()},
        headers=api_headers(email=admin_user.email),
    )
    assert resp.status_code == 200
    by_id = {c["id"]: c for c in resp.json()["clients"]}
    assert by_id[str(client_a.id)]["leads"] == 3 + 5 + 8


def test_f10_t2_paused_onboarding_archived_clients_handled_cleanly_in_overview(
    client, db, tier, admin_user
):
    paused = make_client(db, tier, "Paused Client", status=ClientStatus.PAUSED)
    onboarding = make_client(db, tier, "Onboarding Client", status=ClientStatus.ONBOARDING)
    archived = make_client(db, tier, "Archived Client", status=ClientStatus.ARCHIVED)

    resp = client.get("/v2/clients/overview", headers=api_headers(email=admin_user.email))
    assert resp.status_code == 200
    by_id = {c["id"]: c for c in resp.json()["clients"]}
    assert by_id[str(paused.id)]["status"] == "paused"
    assert by_id[str(onboarding.id)]["status"] == "onboarding"
    assert by_id[str(archived.id)]["status"] == "archived"


def test_f10_t2_zero_previous_period_avoids_division_by_zero_and_returns_null_pct(
    client, db, client_a, admin_user
):
    as_of = date(2026, 10, 30)
    cur_day = date(2026, 10, 20)
    prev_day = date(2026, 9, 15)  # inside previous 30d window

    seed_conversion_def(db, client_a, event_name="generate_lead", conversion_type="lead", active=True)
    # Current period non-zero data
    seed_gsc_daily(db, client_a, cur_day, impressions=1200, clicks=60, position=8.5)
    seed_ga4_traffic(db, client_a, cur_day, 400, channel=OrganicChannel.ORGANIC_SEARCH)
    seed_ga4_event(db, client_a, cur_day, "generate_lead", 10)

    # Prior period explicit zeros -> denominator 0 must yield None, never ZeroDivisionError
    seed_gsc_daily(db, client_a, prev_day, impressions=0, clicks=0, position=0.0)
    seed_ga4_traffic(db, client_a, prev_day, 0, channel=OrganicChannel.ORGANIC_SEARCH)
    seed_ga4_event(db, client_a, prev_day, "generate_lead", 0)
    db.commit()

    resp = client.get(
        "/v2/clients/overview",
        params={"as_of": as_of.isoformat()},
        headers=api_headers(email=admin_user.email),
    )
    assert resp.status_code == 200
    by_id = {c["id"]: c for c in resp.json()["clients"]}
    row = by_id[str(client_a.id)]
    assert row["impressions"] == 1200
    assert row["impressions_change_pct"] is None
    assert row["organic_sessions"] == 400
    assert row["organic_change_pct"] is None
    assert row["leads"] == 10
    assert row["leads_change_pct"] is None
