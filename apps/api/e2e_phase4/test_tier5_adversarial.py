"""Tier 5 E2E Tests: Adversarial Cross-Milestone, Concurrency, Security & Boundary Flows."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.main import app
from app.models.config import ConversionDefinition, OrganicChannel
from app.models.integration import IntegrationProvider
from e2e_phase4.conftest import (
    admin_headers,
    api_headers,
    make_client,
    seed_conversion_def,
    seed_ga4_baseline_window,
    seed_ga4_event,
    seed_ga4_traffic,
    seed_gsc_query_page,
    seed_indexable_site,
    seed_lead_exclusion,
    seed_ser_metric,
    seed_watermark,
    set_integration,
)


def test_t5_e2e_ecommerce_baseline_lock_preserves_conversion_type_and_matches_setup_and_overview(
    client, db, tier, admin_user
):
    c = make_client(
        db,
        tier,
        "Ecommerce Shop",
        domain="ecomshop.example",
        business_model="ecommerce",
    )
    set_integration(db, c, IntegrationProvider.GA4, "properties/888111")
    set_integration(db, c, IntegrationProvider.GSC, "sc-domain:ecomshop.example")
    seed_conversion_def(
        db,
        c,
        event_name="purchase",
        conversion_name="Order Purchase",
        conversion_type="ecommerce",
        active=True,
        is_primary=True,
    )
    seed_ga4_baseline_window(
        db,
        c,
        months=7,
        sessions_per_month=1500,
        direct_sessions_per_month=300,
        leads_per_month=25,
        event_name="purchase",
    )
    recent = date.today() - timedelta(days=2)
    seed_ga4_traffic(db, c, recent, 200, channel=OrganicChannel.ORGANIC_SEARCH, url="/shop")
    seed_ga4_event(db, c, recent, "purchase", 11, channel=OrganicChannel.ORGANIC_SEARCH, url="/checkout")
    db.commit()

    hdrs = admin_headers(c)
    setup = client.get(f"/clients/{c.id}/setup", headers=hdrs)
    assert setup.status_code == 200
    steps = {s["key"]: s for s in setup.json()["steps"]}
    assert steps["leads"]["done"] is True
    assert steps["baseline"]["blocked_by"] is None

    series = client.get(f"/clients/{c.id}/baseline/series", headers=hdrs)
    assert series.status_code == 200, series.text
    assert series.json()["source"]["lead_events"] == ["purchase"]

    lock = client.post(
        f"/clients/{c.id}/baseline/lock",
        headers=hdrs,
        json={"source": "ga4", "months": 24, "lead_events": ["purchase"], "sync_lead_conversions": False},
    )
    assert lock.status_code == 200, lock.text

    db.expire_all()
    row = (
        db.query(ConversionDefinition)
        .filter(ConversionDefinition.client_id == c.id, ConversionDefinition.event_name == "purchase")
        .one()
    )
    assert row.conversion_type == "ecommerce"

    ov = client.get("/v2/clients/overview", headers=api_headers(email=admin_user.email)).json()
    item = next(x for x in ov["clients"] if x["id"] == str(c.id))
    assert item["lead_label"] == "orders"
    assert item["leads"] == 11


def test_t5_e2e_baseline_series_and_pillars_respect_lead_exclusions(client, db, tier):
    c = make_client(db, tier, "Exclusion Baseline Co", business_model="lead_gen")
    seed_conversion_def(db, c, event_name="generate_lead", conversion_type="lead", active=True)
    seed_lead_exclusion(db, c, session_source="qa_bot", reason="Internal QA bot")
    through = date.today() - timedelta(days=1)
    seed_watermark(db, c, "ga4", through)

    for m_offset in range(6, 0, -1):
        day = (date.today().replace(day=15) - timedelta(days=30 * m_offset))
        seed_ga4_traffic(db, c, day, 1000, channel=OrganicChannel.ORGANIC_SEARCH, url="/")
        seed_ga4_event(db, c, day, "generate_lead", 10, session_source="google", url="/contact")
        seed_ga4_event(db, c, day, "generate_lead", 80, session_source="qa_bot", url="/contact")
    seed_ga4_traffic(db, c, through, 1000, channel=OrganicChannel.ORGANIC_SEARCH, url="/")
    seed_ga4_event(db, c, through, "generate_lead", 10, session_source="google", url="/contact")
    seed_ga4_event(db, c, through, "generate_lead", 80, session_source="qa_bot", url="/contact")
    db.commit()

    hdrs = admin_headers(c)
    series = client.get(f"/clients/{c.id}/baseline/series", headers=hdrs)
    assert series.status_code == 200, series.text
    assert all(row["leads"] == 10.0 for row in series.json()["series"])

    pillars = client.get(f"/clients/{c.id}/baseline/pillars", headers=hdrs)
    assert pillars.status_code == 200, pillars.text
    assert pillars.json()["leads"]["total"]["recent_30d"] <= 20.0


def test_t5_e2e_concurrent_watchlist_add_same_new_bucket_and_concurrent_baseline_lock(
    db, engine, tier, admin_user
):
    c = make_client(db, tier, "Concurrent Ops Co")
    previous_override = app.dependency_overrides.get(get_db)

    def thread_safe_get_db():
        with Session(bind=engine) as s:
            yield s

    app.dependency_overrides[get_db] = thread_safe_get_db
    try:
        hdrs = admin_headers(c)
        barrier_wl = threading.Barrier(3)

        def add_kw(i: int):
            with TestClient(app) as tc:
                barrier_wl.wait(timeout=5)
                return tc.post(
                    "/v2/watchlist/keywords",
                    json={"keyword": f"parallel keyword {i}", "bucket_name": "Shared Race Bucket"},
                    headers=hdrs,
                )

        with ThreadPoolExecutor(max_workers=3) as pool:
            wl_res = [f.result() for f in [pool.submit(add_kw, i) for i in range(3)]]
        assert all(r.status_code == 200 for r in wl_res), [(r.status_code, r.text) for r in wl_res]
        assert len({r.json()["bucket_id"] for r in wl_res}) == 1

        csv_text = "\n".join(["month,sessions,leads"] + [f"2026-0{m},1000,15" for m in range(1, 10)])
        barrier_bl = threading.Barrier(3)

        def lock_bl():
            with TestClient(app, raise_server_exceptions=False) as tc:
                barrier_bl.wait(timeout=5)
                return tc.post(
                    f"/clients/{c.id}/baseline/lock",
                    json={"source": "csv", "csv_text": csv_text},
                    headers=hdrs,
                )

        with ThreadPoolExecutor(max_workers=3) as pool:
            bl_res = [f.result() for f in [pool.submit(lock_bl) for _ in range(3)]]
        codes = [r.status_code for r in bl_res]
        assert all(code in (200, 400, 409) for code in codes), codes
        assert codes.count(200) == 1
    finally:
        if previous_override is not None:
            app.dependency_overrides[get_db] = previous_override
        else:
            app.dependency_overrides.pop(get_db, None)


def test_t5_e2e_security_and_boundary_validation(client, db, client_a, admin_user):
    hdrs = admin_headers(client_a)

    # Optimizer SSRF / XSS scheme rejection
    for bad_url in ("javascript:alert(1)", "http://127.0.0.1/admin", "http://169.254.169.254/latest"):
        assert client.get("/v2/optimizer/page", params={"url": bad_url}, headers=hdrs).status_code in (400, 422)
        assert (
            client.post(
                "/v2/optimizer/draft",
                json={"url": bad_url, "kind": "opening", "depth": "quick", "keyword": "test"},
                headers=hdrs,
            ).status_code
            in (400, 422)
        )

    # Watchlist CSV import overflow / inf / negative / oversized cell handling (never 500)
    csv_text = (
        "Topic,Keyword,Volume,Difficulty\n"
        f"Core,valid term,500,20\n"
        f"Core,overflow vol,99999999999999,20\n"
        f"Core,inf vol,inf,20\n"
        f"Core,neg vol,-10,20\n"
        f"Core,{'x' * 405},500,20\n"
    )
    imp = client.post("/v2/watchlist/import", json={"csv_text": csv_text}, headers=hdrs)
    assert imp.status_code == 200, imp.text
    assert len(imp.json()["warnings"]) == 3
    assert len(imp.json()["skipped"]) == 1

    # Overview as_of min bound -> 422
    ov_bad = client.get(
        "/v2/clients/overview",
        params={"as_of": "0001-01-15"},
        headers=api_headers(email=admin_user.email),
    )
    assert ov_bad.status_code == 422


def test_t5_e2e_content_gaps_crack_hiring_and_short_domain_and_case_ignore(client, db, tier, admin_user):
    c = make_client(
        db,
        tier,
        "Foundation Fix Co",
        domain="foundationfix.example",
        competitor_domains=["air.com", "seo.com", "pro.com"],
    )
    recent = date.today() - timedelta(days=2)
    seed_indexable_site(db, c, count=10, snap_date=recent)
    for query in (
        "foundation crack monitoring",
        "hiring foundation contractor",
        "air circulation crawl space",
    ):
        seed_gsc_query_page(db, c, recent, query, 380, 18.0, clicks=6, url=f"https://{c.domain}/services/item-1")
        seed_ser_metric(db, c, query, volume=600, difficulty=25)
    db.commit()

    hdrs = admin_headers(c)
    gaps_res = client.get("/v2/content/gaps", headers=hdrs)
    assert gaps_res.status_code == 200
    terms = {g["term"] for g in gaps_res.json()["gaps"]}
    assert {
        "foundation crack monitoring",
        "hiring foundation contractor",
        "air circulation crawl space",
    } <= terms

    # Mixed-case ignore + restore
    ign = client.post(
        "/v2/content/ignore",
        json={"area": "gap", "key": "  Foundation Crack   Monitoring "},
        headers=hdrs,
    )
    assert ign.status_code == 200
    live = client.get("/v2/content/gaps", headers=hdrs).json()
    assert "foundation crack monitoring" not in {g["term"] for g in live["gaps"]}
    assert live["ignored_total"] == 1


def test_t5_e2e_mixed_ecommerce_and_lingering_lead_baseline_lock_and_review_parity(
    client, db, tier, admin_user
):
    c = make_client(
        db,
        tier,
        "Mixed Ecom Shop",
        domain="mixedecom.example",
        business_model="ecommerce",
    )
    set_integration(db, c, IntegrationProvider.GA4, "properties/999111")
    seed_conversion_def(
        db,
        c,
        event_name="purchase",
        conversion_name="Order Purchase",
        conversion_type="ecommerce",
        active=True,
        is_primary=True,
    )
    seed_conversion_def(
        db,
        c,
        event_name="generate_lead",
        conversion_name="Lingering Lead",
        conversion_type="lead",
        active=True,
        is_primary=False,
    )
    through = date(2026, 9, 30)
    seed_watermark(db, c, "ga4", through)
    for m in range(1, 10):
        day = date(2026, m, 15)
        seed_ga4_traffic(db, c, day, 1000, channel=OrganicChannel.ORGANIC_SEARCH, url="/shop")
        seed_ga4_event(db, c, day, "purchase", 20, channel=OrganicChannel.ORGANIC_SEARCH, url="/checkout")
        seed_ga4_event(db, c, day, "generate_lead", 5, channel=OrganicChannel.ORGANIC_SEARCH, url="/contact")
    db.commit()

    hdrs = admin_headers(c)
    events = client.get(f"/clients/{c.id}/baseline/events", headers=hdrs)
    assert events.status_code == 200
    assert events.json()["defaults"] == ["purchase"]

    lock = client.post(
        f"/clients/{c.id}/baseline/lock",
        headers=hdrs,
        json={
            "source": "ga4",
            "regime_start": "2026-02",
            "lead_events": ["purchase"],
            "sync_lead_conversions": False,
        },
    )
    assert lock.status_code == 200, lock.text
    assert lock.json()["lead_conversions_changed"] is None
    assert lock.json()["version"]["monthly_leads"] == 20.0

    db.expire_all()
    purchase_row = (
        db.query(ConversionDefinition)
        .filter(ConversionDefinition.client_id == c.id, ConversionDefinition.event_name == "purchase")
        .one()
    )
    assert purchase_row.conversion_type == "ecommerce"

    lc = client.post(
        f"/clients/{c.id}/baseline/lead-conversions",
        headers=hdrs,
        json={"lead_events": ["purchase"]},
    )
    assert lc.status_code == 200
    assert lc.json()["lead_events"] == ["purchase"]

    ov = client.get(
        "/v2/clients/overview",
        params={"as_of": through.isoformat()},
        headers=api_headers(email=admin_user.email),
    ).json()
    item = next(x for x in ov["clients"] if x["id"] == str(c.id))
    assert item["leads"] == 20

    review = client.get("/v2/review", params={"month": "2026-09"}, headers=hdrs)
    assert review.status_code == 200, review.text
    assert review.json()["conversions"]["current"] == 20.0


def test_t5_e2e_lead_gen_call_deselection_and_dashboard_parity(client, db, tier, admin_user):
    c = make_client(
        db,
        tier,
        "Lead Plus Call Co",
        domain="leadcall.example",
        business_model="lead_gen",
    )
    set_integration(db, c, IntegrationProvider.GA4, "properties/999222")
    seed_conversion_def(
        db,
        c,
        event_name="generate_lead",
        conversion_name="Lead",
        conversion_type="lead",
        active=True,
        is_primary=True,
    )
    seed_conversion_def(
        db,
        c,
        event_name="phone_call",
        conversion_name="Phone Call",
        conversion_type="call",
        active=True,
        is_primary=False,
    )
    through = date(2026, 9, 30)
    seed_watermark(db, c, "ga4", through)
    for m in range(1, 10):
        day = date(2026, m, 15)
        seed_ga4_traffic(db, c, day, 1000, channel=OrganicChannel.ORGANIC_SEARCH, url="/")
        seed_ga4_event(db, c, day, "generate_lead", 10, channel=OrganicChannel.ORGANIC_SEARCH, url="/contact")
        seed_ga4_event(db, c, day, "phone_call", 7, channel=OrganicChannel.ORGANIC_SEARCH, url="/contact")
    db.commit()

    hdrs = admin_headers(c)
    refused = client.post(
        f"/clients/{c.id}/baseline/lock",
        headers=hdrs,
        json={
            "source": "ga4",
            "regime_start": "2026-02",
            "lead_events": ["generate_lead"],
            "sync_lead_conversions": False,
        },
    )
    assert refused.status_code == 400
    assert "phone_call" in refused.json()["detail"]

    agreed = client.post(
        f"/clients/{c.id}/baseline/lock",
        headers=hdrs,
        json={
            "source": "ga4",
            "regime_start": "2026-02",
            "lead_events": ["generate_lead"],
            "sync_lead_conversions": True,
        },
    )
    assert agreed.status_code == 200, agreed.text
    assert agreed.json()["version"]["monthly_leads"] == 10.0

    db.expire_all()
    call_row = (
        db.query(ConversionDefinition)
        .filter(ConversionDefinition.client_id == c.id, ConversionDefinition.event_name == "phone_call")
        .one()
    )
    assert call_row.active is False
    assert call_row.conversion_type == "call"

    ov = client.get(
        "/v2/clients/overview",
        params={"as_of": through.isoformat()},
        headers=api_headers(email=admin_user.email),
    ).json()
    item = next(x for x in ov["clients"] if x["id"] == str(c.id))
    assert item["leads"] == 10

    review = client.get("/v2/review", params={"month": "2026-09"}, headers=hdrs)
    assert review.status_code == 200, review.text
    assert review.json()["conversions"]["current"] == 10.0


def test_t5_e2e_nul_bytes_concurrent_csv_and_noncanonical_ipv4(db, engine, tier):
    c = make_client(db, tier, "Hardening E2E Co", domain="hardening.example")
    hdrs = admin_headers(c)

    previous_override = app.dependency_overrides.get(get_db)

    def thread_safe_get_db():
        with Session(bind=engine) as s:
            yield s

    app.dependency_overrides[get_db] = thread_safe_get_db
    try:
        with TestClient(app) as tc:
            assert (
                tc.post(
                    "/v2/watchlist/keywords",
                    json={"keyword": "bad\x00kw", "bucket_name": "Core"},
                    headers=hdrs,
                ).status_code
                == 422
            )
            imp = tc.post(
                "/v2/watchlist/import",
                json={"csv_text": "Topic,Keyword,Volume\nCore,clean\x00term,200\nCore,\x00,50\n"},
                headers=hdrs,
            )
            assert imp.status_code == 200, imp.text
            assert imp.json()["keywords_created"] == 1

            for bad_ip_url in (
                "http://0177.0.0.1/admin",
                "http://0x7f.0.0.1/admin",
                "http://127.1/admin",
                "http://224.0.0.1/admin",
                "http://[ff02::1]/admin",
                "http://[::ffff:224.0.0.1]/admin",
            ):
                assert (
                    tc.post(
                        "/v2/optimizer/draft",
                        json={"url": bad_ip_url, "kind": "opening", "depth": "quick", "keyword": "test"},
                        headers=hdrs,
                    ).status_code
                    == 422
                )
    finally:
        if previous_override is not None:
            app.dependency_overrides[get_db] = previous_override
        else:
            app.dependency_overrides.pop(get_db, None)


def test_t5_e2e_nul_bytes_across_phase4_endpoints_and_multicast_ip_rejected(client, db, tier):
    c = make_client(db, tier, "Nul Guard E2E Co", domain="nulguard.example")
    recent = date.today() - timedelta(days=2)
    seed_gsc_query_page(
        db,
        c,
        recent,
        "drain cleaning service",
        300,
        12.0,
        clicks=8,
        url=f"https://{c.domain}/drain-cleaning",
    )
    db.commit()
    hdrs = admin_headers(c)

    # 1. POST /v2/optimizer/draft (NUL in text and url) -> 422
    assert (
        client.post(
            "/v2/optimizer/draft",
            json={
                "url": f"https://{c.domain}/drain-cleaning",
                "kind": "opening",
                "depth": "quick",
                "keyword": "drain",
                "text": "hello\x00world",
            },
            headers=hdrs,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v2/optimizer/draft",
            json={
                "url": f"https://{c.domain}/a\x00b",
                "kind": "opening",
                "depth": "quick",
                "keyword": "drain",
            },
            headers=hdrs,
        ).status_code
        == 422
    )

    # 2. GET /v2/optimizer/page?url=...\x00... -> 422
    assert (
        client.get(
            "/v2/optimizer/page",
            params={"url": f"https://{c.domain}/a\x00b"},
            headers=hdrs,
        ).status_code
        == 422
    )

    # 3. GET /v2/watchlist/suggestions?search=a\x00b -> 422 (with real FactGscQueryPage data)
    assert (
        client.get(
            "/v2/watchlist/suggestions",
            params={"search": "a\x00b"},
            headers=hdrs,
        ).status_code
        == 422
    )
    ok_sug = client.get(
        "/v2/watchlist/suggestions",
        params={"search": "drain"},
        headers=hdrs,
    )
    assert ok_sug.status_code == 200
    assert [s["key"] for s in ok_sug.json()["suggestions"]] == ["drain cleaning service"]

    # 4. POST /v2/content/ignore -> 422
    assert (
        client.post(
            "/v2/content/ignore",
            json={"area": "gap", "key": "bad\x00key"},
            headers=hdrs,
        ).status_code
        == 422
    )

    # 5. GET /v2/content/gaps/brief?term=foo\x00bar (+ sibling refresh endpoints) -> 422
    assert (
        client.get(
            "/v2/content/gaps/brief",
            params={"term": "foo\x00bar"},
            headers=hdrs,
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/v2/content/refreshes/page",
            params={"url": f"https://{c.domain}/a\x00b"},
            headers=hdrs,
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/v2/content/refreshes/search",
            params={"query": "foo\x00bar"},
            headers=hdrs,
        ).status_code
        == 422
    )

    # 6. POST /clients/{id}/baseline/lead-conversions & /baseline/lock -> 422
    assert (
        client.post(
            f"/clients/{c.id}/baseline/lead-conversions",
            json={"lead_events": ["bad\x00event"]},
            headers=hdrs,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/clients/{c.id}/baseline/lock",
            json={"source": "ga4", "lead_events": ["bad\x00event"]},
            headers=hdrs,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/clients/{c.id}/baseline/lock",
            json={"source": "ga4", "reason_code": "correction", "reason_note": "bad\x00note text"},
            headers=hdrs,
        ).status_code
        == 422
    )

    # 7. Multicast IPv4/IPv6 rejected on both optimizer endpoints -> 422
    for mcast_url in ("http://224.0.0.1/admin", "http://[ff02::1]/admin"):
        assert (
            client.get("/v2/optimizer/page", params={"url": mcast_url}, headers=hdrs).status_code
            == 422
        )
        assert (
            client.post(
                "/v2/optimizer/draft",
                json={"url": mcast_url, "kind": "opening", "depth": "quick", "keyword": "test"},
                headers=hdrs,
            ).status_code
            == 422
        )
