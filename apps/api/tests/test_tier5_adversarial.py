"""Tier-5 Adversarial Unit & Integration Tests (M7 Phase 2 Hardening)."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.settings import get_settings
from app.core.urls import public_host_or_error, url_variants
from app.decisions.content_gaps import is_noise_query
from app.main import app
from app.models.baseline import BaselineVersion
from app.models.client import Client
from app.models.config import ConversionDefinition, LeadExclusion, OrganicChannel
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscQueryPage
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.models.job import DataWatermark, ValidationStatus
from app.models.schema_tools import ContentState
from app.models.seranking import FactSerKeywordMetric
from app.services import (
    baseline_lock,
    baseline_pillars,
    baseline_series,
    client_setup,
    dashboard,
    decision_measurements,
    demand_gaps,
    lead_conversions,
)
from tests.conftest import auth_header, client_header


def _seed_foundation_site(db: Session, client: Client, day: date) -> None:
    pages = [
        ("foundation-crack-repair", "Foundation Crack Repair"),
        ("crawl-space-encapsulation", "Crawl Space Encapsulation"),
        ("basement-waterproofing", "Basement Waterproofing"),
        ("structural-piering", "Helical Pier Underpinning"),
        ("bowing-wall-stabilization", "Bowing Wall Stabilization"),
        ("sump-pump-install", "Sump Pump Installation"),
        ("moisture-barriers", "Vapor Barrier Systems"),
        ("slab-jacking", "Concrete Slab Leveling"),
        ("french-drains", "Interior French Drain Systems"),
        ("crawl-space-dehumidifier", "Crawl Space Dehumidification"),
    ]
    for slug, title in pages:
        url = f"https://{client.domain}/{slug}"
        db.add(
            FactCrawlPageSnapshot(
                id=uuid.uuid4(),
                client_id=client.id,
                source=CRAWL_SOURCE_FIRST_PARTY,
                snapshot_date=day,
                raw_url=url,
                normalized_url=url,
                status_code=200,
                indexable=True,
                word_count=800,
                inbound_internal_links=4,
                inbound_editorial_links=2,
                redirect_count=0,
                title=title,
                sections=[{"heading": title}],
            )
        )


def test_t5_content_gaps_preserves_crack_repair_and_hiring_contractor_queries():
    kept = [
        "foundation crack monitoring",
        "concrete wall crack repair",
        "gunite-crack",
        "hiring foundation contractor",
        "hiring a plumber",
    ]
    for q in kept:
        assert is_noise_query(q) is False, f"Legitimate service query {q!r} dropped as noise"

    noisy = [
        "careers",
        "job openings",
        "we are hiring",
        "now hiring",
        "hiring manager",
        "software crack",
        "crack download",
        "photoshop crack",
        "keygen",
        "torrent",
    ]
    for q in noisy:
        assert is_noise_query(q) is True, f"True noise query {q!r} escaped noise filter"


def test_t5_three_char_competitor_domain_does_not_drop_generic_industry_terms(db: Session, client_a: Client):
    today = date(2026, 11, 20)
    client_a.client_name = "Aero Foundation"
    client_a.domain = "aerofoundation.example"
    client_a.competitor_domains = ["seo.com", "air.com", "pro.com"]
    _seed_foundation_site(db, client_a, today - timedelta(days=2))
    # Add an SEO marketing page only on a separate check or keep crawlspace focus:
    # "air circulation crawl space" is relevant to crawl space & must NOT be tagged demand_brand.
    # "seo marketing cost" is off-topic on a foundation site, NOT demand_brand.
    # "air.com reviews" and "seo pricing" ARE rival-brand navigational.
    queries = [
        ("air circulation crawl space", 350, 22.0),
        ("seo marketing cost", 300, 22.0),
        ("air.com reviews", 280, 18.0),
        ("seo pricing", 280, 18.0),
        ("pro complaints", 250, 18.0),
    ]
    for query, imp, pos in queries:
        db.add(
            FactGscQueryPage(
                client_id=client_a.id,
                date=today - timedelta(days=3),
                query=query,
                raw_url=f"https://{client_a.domain}/crawl-space-encapsulation",
                normalized_url=f"https://{client_a.domain}/crawl-space-encapsulation",
                country="usa",
                device="DESKTOP",
                impressions=Decimal(imp),
                clicks=Decimal(5),
                ctr=Decimal("0.02"),
                average_position=Decimal(str(pos)),
            )
        )
    db.commit()

    candidates, summary, blocked = demand_gaps.demand_candidates(db, client_a, today=today)
    assert blocked is None
    terms = {g.term for g in candidates}
    assert "air circulation crawl space" in terms
    assert summary["demand_off_topic"] == 1  # seo marketing cost -> off_topic, NOT brand
    assert summary["demand_brand"] == 3  # air.com reviews, seo pricing, pro complaints


def test_t5_setup_leads_step_ecommerce_and_engagement_alignment(client, db: Session, client_a: Client, admin_user):
    from tests.ga4_seed import _daily_facts, _watermark

    client_a.business_model = "ecommerce"
    _watermark(db, client_a.id, date(2026, 9, 30))
    _daily_facts(db, client_a.id, start=date(2026, 1, 1), days=273, sessions=100, leads=0)

    # Engagement-only should NOT mark leads done or unblock baseline
    eng = ConversionDefinition(
        client_id=client_a.id,
        event_name="scroll_90",
        conversion_name="Scroll 90",
        conversion_type="engagement",
        active=True,
    )
    db.add(eng)
    db.commit()

    state_eng = client_setup.setup_state(db, client_a)
    steps_eng = {s["key"]: s for s in state_eng["steps"]}
    assert steps_eng["leads"]["done"] is False
    assert steps_eng["baseline"]["blocked_by"] == "needs lead definitions"

    # Adding active ecommerce conversion unblocks both setup AND baseline/series + preserves type on lock
    purchase = ConversionDefinition(
        client_id=client_a.id,
        event_name="purchase",
        conversion_name="Purchase",
        conversion_type="ecommerce",
        active=True,
        is_primary=True,
    )
    db.add(purchase)
    for m in range(1, 10):
        db.add(
            FactGa4Event(
                id=uuid.uuid4(),
                client_id=client_a.id,
                date=date(2026, m, 15),
                raw_url="https://x.test/checkout",
                normalized_url="https://x.test/checkout",
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                event_name="purchase",
                event_count=12,
            )
        )
    db.commit()

    state_ecom = client_setup.setup_state(db, client_a)
    steps_ecom = {s["key"]: s for s in state_ecom["steps"]}
    assert steps_ecom["leads"]["done"] is True
    assert steps_ecom["baseline"]["blocked_by"] is None

    headers = client_header(client_a.id, admin_user.email)
    series_res = client.get(f"/clients/{client_a.id}/baseline/series", headers=headers)
    assert series_res.status_code == 200, series_res.text
    assert series_res.json()["source"]["lead_events"] == ["purchase"]

    lock_res = client.post(
        f"/clients/{client_a.id}/baseline/lock",
        headers=headers,
        json={"source": "ga4", "lead_events": ["purchase"], "sync_lead_conversions": True},
    )
    assert lock_res.status_code == 200, lock_res.text
    db.expire_all()
    refreshed_purchase = (
        db.query(ConversionDefinition)
        .filter(ConversionDefinition.client_id == client_a.id, ConversionDefinition.event_name == "purchase")
        .one()
    )
    assert refreshed_purchase.conversion_type == "ecommerce"
    assert refreshed_purchase.active is True


def test_t5_baseline_series_and_pillars_apply_lead_exclusions(client, db: Session, client_a: Client, admin_user):
    through = date(2026, 9, 30)
    db.add(
        ConversionDefinition(
            client_id=client_a.id,
            event_name="generate_lead",
            conversion_name="Lead",
            conversion_type="lead",
            active=True,
            is_primary=True,
        )
    )
    db.add(
        DataWatermark(
            client_id=client_a.id,
            source="ga4",
            fact_through_date=through,
            validation_status=ValidationStatus.PASSED,
        )
    )
    db.add(
        LeadExclusion(
            id=uuid.uuid4(),
            client_id=client_a.id,
            session_source="qa_bot",
            reason="Internal QA traffic",
        )
    )
    for m in range(1, 10):
        day = date(2026, m, 10)
        db.add(
            FactGa4Traffic(
                id=uuid.uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url="https://x.test/",
                normalized_url="https://x.test/",
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                sessions=Decimal("1000"),
                active_users=Decimal("800"),
                views=Decimal("1200"),
            )
        )
        db.add(
            FactGa4Event(
                id=uuid.uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url="https://x.test/contact",
                normalized_url="https://x.test/contact",
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                event_name="generate_lead",
                event_count=10,
            )
        )
        db.add(
            FactGa4Event(
                id=uuid.uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url="https://x.test/contact",
                normalized_url="https://x.test/contact",
                session_source="qa_bot",
                session_medium="none",
                channel=OrganicChannel.DIRECT_UNATTRIBUTED,
                event_name="generate_lead",
                event_count=90,
            )
        )
    db.commit()

    rows, _ = baseline_series.series_from_ga4(db, client_a)
    assert all(r.leads == 10.0 for r in rows)

    pillars = baseline_pillars.build_pillars_snapshot(db, client_a, as_of=through)
    assert pillars["leads"]["total"]["total_90d"] == 30.0
    assert pillars["leads"]["total"]["recent_30d"] == 10.0


def test_t5_goal_state_handles_none_projection_or_snapshot(db: Session, client_a: Client):
    db.add(
        BaselineVersion(
            client_id=client_a.id,
            version=1,
            reason_code="initial",
            locked_by="admin@smamarketing.com",
            status="draft",
            method_version="1.0",
            source_type="csv",
            window_from="2026-01",
            window_to="2026-09",
            lead_events=[],
            acknowledged=[],
            monthly_sessions=Decimal("1000"),
            lead_rate_pct=Decimal("2.0"),
            monthly_leads=Decimal("20"),
            goal_monthly_leads=Decimal("20"),
            snapshot={"projection": {"suggested_monthly_lead_goal": None}},
        )
    )
    db.commit()
    state = baseline_lock.goal_state(db, client_a)
    assert state["suggested"] is None
    assert state["version"] == 1


def test_t5_concurrent_add_keyword_same_new_bucket_succeeds(engine, client_a: Client, admin_user):
    previous_override = app.dependency_overrides.get(get_db)

    def thread_safe_get_db():
        with Session(bind=engine) as s:
            yield s

    app.dependency_overrides[get_db] = thread_safe_get_db
    try:
        headers = client_header(client_a.id, admin_user.email)
        barrier = threading.Barrier(4)

        def call_add(idx: int):
            with TestClient(app) as tc:
                barrier.wait(timeout=5)
                return tc.post(
                    "/v2/watchlist/keywords",
                    json={"keyword": f"concurrent term {idx}", "bucket_name": "Same New Bucket"},
                    headers=headers,
                )

        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = [f.result() for f in [pool.submit(call_add, i) for i in range(4)]]
    finally:
        if previous_override is not None:
            app.dependency_overrides[get_db] = previous_override
        else:
            app.dependency_overrides.pop(get_db, None)

    assert all(r.status_code == 200 for r in responses), [(r.status_code, r.text) for r in responses]
    bucket_ids = {r.json()["bucket_id"] for r in responses}
    assert len(bucket_ids) == 1


def test_t5_concurrent_baseline_lock_does_not_500(engine, client_a: Client, admin_user):
    previous_override = app.dependency_overrides.get(get_db)

    def thread_safe_get_db():
        with Session(bind=engine) as s:
            yield s

    app.dependency_overrides[get_db] = thread_safe_get_db
    csv_text = "\n".join(
        ["month,sessions,leads"] + [f"2026-0{m},1000,15" for m in range(1, 10)]
    )
    try:
        headers = client_header(client_a.id, admin_user.email)
        barrier = threading.Barrier(4)

        def call_lock():
            with TestClient(app, raise_server_exceptions=False) as tc:
                barrier.wait(timeout=5)
                return tc.post(
                    f"/clients/{client_a.id}/baseline/lock",
                    json={"source": "csv", "csv_text": csv_text},
                    headers=headers,
                )

        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = [f.result() for f in [pool.submit(call_lock) for _ in range(4)]]
    finally:
        if previous_override is not None:
            app.dependency_overrides[get_db] = previous_override
        else:
            app.dependency_overrides.pop(get_db, None)

    statuses = [r.status_code for r in responses]
    assert all(code in (200, 400, 409) for code in statuses), statuses
    assert statuses.count(200) == 1


def test_t5_optimizer_rejects_invalid_scheme_and_non_public_urls(client, client_a: Client, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    bad_urls = [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/admin",
        "http://localhost:8000/secret",
        "http://10.0.0.5/internal",
    ]
    for bad in bad_urls:
        page_res = client.get("/v2/optimizer/page", params={"url": bad}, headers=headers)
        assert page_res.status_code in (400, 422), (bad, page_res.status_code, page_res.text)
        draft_res = client.post(
            "/v2/optimizer/draft",
            json={"url": bad, "kind": "opening", "depth": "quick", "keyword": "test"},
            headers=headers,
        )
        assert draft_res.status_code in (400, 422), (bad, draft_res.status_code, draft_res.text)


def test_t5_watchlist_import_rejects_overflow_inf_negative_and_oversized_cells(
    client, db: Session, client_a: Client, admin_user
):
    headers = client_header(client_a.id, admin_user.email)
    long_kw = "k" * 405
    long_topic = "t" * 165
    long_intent = "i" * 125
    csv_text = (
        "Topic,Keyword,Volume,Difficulty,Intent\n"
        f"Valid Bucket,overflow vol,99999999999999,20,commercial\n"
        f"Valid Bucket,inf vol,inf,20,commercial\n"
        f"Valid Bucket,neg vol,-50,20,commercial\n"
        f"Valid Bucket,long intent term,500,20,{long_intent}\n"
        f"Valid Bucket,{long_kw},500,20,commercial\n"
        f"{long_topic},topic too long term,500,20,commercial\n"
    )
    res = client.post("/v2/watchlist/import", json={"csv_text": csv_text}, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["warnings"]) == 4
    assert len(body["skipped"]) == 2
    assert body["keywords_created"] == 4

    wl = client.get("/v2/watchlist", headers=headers).json()
    kws = {k["keyword"]: k for b in wl["buckets"] for k in b["keywords"]}
    assert kws["overflow vol"]["volume"] is None
    assert kws["inf vol"]["volume"] is None
    assert kws["neg vol"]["volume"] is None
    assert kws["long intent term"]["intent"] is None


def test_t5_watchlist_patch_rejects_blank_bucket_name_422(client, client_a: Client, admin_user):
    headers = client_header(client_a.id, admin_user.email)
    created = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "drain repair", "bucket_name": "Plumbing"},
        headers=headers,
    ).json()
    res = client.patch(
        f"/v2/watchlist/keywords/{created['id']}",
        json={"bucket_name": "   "},
        headers=headers,
    )
    assert res.status_code == 422


def test_t5_overview_as_of_min_date_422_and_call_conversion_included(
    client, db: Session, client_a: Client, admin_user
):
    bad = client.get(
        "/v2/clients/overview",
        params={"as_of": "0001-01-15"},
        headers=auth_header(admin_user.email),
    )
    assert bad.status_code == 422

    as_of = date(2026, 11, 20)
    cur_day = as_of - timedelta(days=2)
    client_a.business_model = "lead_gen"
    db.add(
        ConversionDefinition(
            id=uuid.uuid4(),
            client_id=client_a.id,
            event_name="phone_call",
            conversion_name="Phone Call",
            conversion_type="call",
            active=True,
        )
    )
    db.add(
        FactGa4Traffic(
            id=uuid.uuid4(),
            client_id=client_a.id,
            date=cur_day,
            raw_url="https://x.test/",
            normalized_url="https://x.test/",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=Decimal("200"),
            active_users=Decimal("180"),
            views=Decimal("250"),
        )
    )
    db.add(
        FactGa4Event(
            id=uuid.uuid4(),
            client_id=client_a.id,
            date=cur_day,
            raw_url="https://x.test/contact",
            normalized_url="https://x.test/contact",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="phone_call",
            event_count=9,
        )
    )
    db.commit()

    ok = client.get(
        "/v2/clients/overview",
        params={"as_of": as_of.isoformat()},
        headers=auth_header(admin_user.email),
    )
    assert ok.status_code == 200
    row = next(r for r in ok.json()["clients"] if r["id"] == str(client_a.id))
    assert row["leads"] == 9


def test_t5_content_ignore_normalizes_case_and_ignored_total_matches_view(
    client, db: Session, client_a: Client, admin_user
):
    today = date.today()
    _seed_foundation_site(db, client_a, today - timedelta(days=2))
    db.add(
        FactGscQueryPage(
            client_id=client_a.id,
            date=today - timedelta(days=3),
            query="crawl space dehumidifier sizing",
            raw_url=f"https://{client_a.domain}/crawl-space-dehumidifier",
            normalized_url=f"https://{client_a.domain}/crawl-space-dehumidifier",
            country="usa",
            device="DESKTOP",
            impressions=Decimal("400"),
            clicks=Decimal("10"),
            ctr=Decimal("0.025"),
            average_position=Decimal("18.0"),
        )
    )
    db.add(
        FactSerKeywordMetric(
            id=uuid.uuid4(),
            client_id=client_a.id,
            keyword="crawl space dehumidifier sizing",
            source="us",
            volume=500,
            difficulty=25,
            data_found=True,
            fetched_at=today,
        )
    )
    # Also seed a stale ContentState(area="gap") for a term that is NOT in active gaps
    db.add(
        ContentState(
            client_id=client_a.id,
            area="gap",
            key="stale vanished term",
            created_by=admin_user.email,
        )
    )
    db.commit()

    headers = client_header(client_a.id, admin_user.email)
    res_ignore = client.post(
        "/v2/content/ignore",
        json={"area": "gap", "key": "  Crawl Space   Dehumidifier Sizing  "},
        headers=headers,
    )
    assert res_ignore.status_code == 200

    live = client.get("/v2/content/gaps", headers=headers).json()
    assert [g["term"] for g in live["gaps"]] == []
    assert live["ignored_total"] == 1  # excludes stale vanished term

    ignored_view = client.get("/v2/content/gaps", params={"ignored": True}, headers=headers).json()
    assert [g["term"] for g in ignored_view["gaps"]] == ["crawl space dehumidifier sizing"]

    # Mixed-case restore removes the normalized gap
    res_restore = client.post(
        "/v2/content/restore",
        json={"area": "gap", "key": "CRAWL SPACE DEHUMIDIFIER SIZING"},
        headers=headers,
    )
    assert res_restore.status_code == 200
    after = client.get("/v2/content/gaps", headers=headers).json()
    assert [g["term"] for g in after["gaps"]] == ["crawl space dehumidifier sizing"]
    assert after["ignored_total"] == 0


def test_t5_suggestions_excludes_noise_and_rival_navigational(client, db: Session, client_a: Client, admin_user):
    integ = (
        db.query(Integration)
        .filter(Integration.client_id == client_a.id, Integration.provider == IntegrationProvider.GSC)
        .one()
    )
    integ.connection_status = ConnectionStatus.CONNECTED
    integ.external_property_id = "sc-domain:clienta.example"
    client_a.competitor_domains = ["rivalplumbing.com"]
    today = date(2026, 10, 28)
    for query, imp in [
        ("wp-admin", 400),
        ("careers", 350),
        ("rivalplumbing reviews", 300),
        ("emergency pipe repair", 320),
    ]:
        db.add(
            FactGscQueryPage(
                client_id=client_a.id,
                date=today - timedelta(days=2),
                query=query,
                raw_url=f"https://{client_a.domain}/pipes",
                normalized_url=f"https://{client_a.domain}/pipes",
                country="usa",
                device="DESKTOP",
                impressions=Decimal(imp),
                clicks=Decimal(5),
                ctr=Decimal("0.02"),
                average_position=Decimal("12.0"),
            )
        )
    db.commit()

    res = client.get("/v2/watchlist/suggestions", headers=client_header(client_a.id, admin_user.email))
    assert res.status_code == 200
    keys = [s["key"] for s in res.json()["suggestions"]]
    assert keys == ["emergency pipe repair"]


def test_t5_mixed_ecommerce_and_lingering_lead_baseline_lock_no_deadlock(
    client, db: Session, client_a: Client, admin_user
):
    through = date(2026, 9, 30)
    client_a.business_model = "ecommerce"
    db.add(
        DataWatermark(
            client_id=client_a.id,
            source="ga4",
            fact_through_date=through,
            validation_status=ValidationStatus.PASSED,
        )
    )
    db.add_all(
        [
            ConversionDefinition(
                client_id=client_a.id,
                event_name="purchase",
                conversion_name="Purchase",
                conversion_type="ecommerce",
                active=True,
                is_primary=True,
            ),
            ConversionDefinition(
                client_id=client_a.id,
                event_name="generate_lead",
                conversion_name="Lead",
                conversion_type="lead",
                active=True,
                is_primary=False,
            ),
        ]
    )
    for m in range(1, 10):
        day = date(2026, m, 15)
        db.add(
            FactGa4Traffic(
                id=uuid.uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url="https://x.test/",
                normalized_url="https://x.test/",
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                sessions=Decimal("1000"),
                active_users=Decimal("800"),
                views=Decimal("1200"),
            )
        )
        db.add(
            FactGa4Event(
                id=uuid.uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url="https://x.test/checkout",
                normalized_url="https://x.test/checkout",
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                event_name="purchase",
                event_count=20,
            )
        )
        db.add(
            FactGa4Event(
                id=uuid.uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url="https://x.test/contact",
                normalized_url="https://x.test/contact",
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                event_name="generate_lead",
                event_count=5,
            )
        )
    db.commit()

    assert lead_conversions.diff(db, client_a.id, ["purchase"]) == {
        "add": [],
        "remove": [],
        "keep": ["purchase"],
    }

    headers = client_header(client_a.id, admin_user.email)
    events_res = client.get(f"/clients/{client_a.id}/baseline/events", headers=headers)
    assert events_res.status_code == 200
    assert events_res.json()["defaults"] == ["purchase"]

    lock_res = client.post(
        f"/clients/{client_a.id}/baseline/lock",
        headers=headers,
        json={
            "source": "ga4",
            "regime_start": "2026-02",
            "lead_events": ["purchase"],
            "sync_lead_conversions": False,
        },
    )
    assert lock_res.status_code == 200, lock_res.text
    assert lock_res.json()["lead_conversions_changed"] is None

    db.expire_all()
    purchase_row = (
        db.query(ConversionDefinition)
        .filter(ConversionDefinition.client_id == client_a.id, ConversionDefinition.event_name == "purchase")
        .one()
    )
    assert purchase_row.conversion_type == "ecommerce"
    assert purchase_row.active is True

    lc_res = client.post(
        f"/clients/{client_a.id}/baseline/lead-conversions",
        headers=headers,
        json={"lead_events": ["purchase"]},
    )
    assert lc_res.status_code == 200, lc_res.text
    assert lc_res.json()["lead_events"] == ["purchase"]

    # Activating a new event on an ecommerce client creates it as ecommerce and returns it cleanly.
    lc_add = client.post(
        f"/clients/{client_a.id}/baseline/lead-conversions",
        headers=headers,
        json={"lead_events": ["purchase", "checkout_complete"]},
    )
    assert lc_add.status_code == 200, lc_add.text
    assert lc_add.json()["lead_events"] == ["checkout_complete", "purchase"]
    db.expire_all()
    checkout_row = (
        db.query(ConversionDefinition)
        .filter(
            ConversionDefinition.client_id == client_a.id,
            ConversionDefinition.event_name == "checkout_complete",
        )
        .one()
    )
    assert checkout_row.conversion_type == "ecommerce"


def test_t5_lead_gen_call_deselection_on_lock_matches_overview_setup_series_pillars(
    client, db: Session, client_a: Client, admin_user
):
    through = date(2026, 9, 30)
    client_a.business_model = "lead_gen"
    db.add(
        DataWatermark(
            client_id=client_a.id,
            source="ga4",
            fact_through_date=through,
            validation_status=ValidationStatus.PASSED,
        )
    )
    db.add_all(
        [
            ConversionDefinition(
                client_id=client_a.id,
                event_name="generate_lead",
                conversion_name="Lead",
                conversion_type="lead",
                active=True,
                is_primary=True,
            ),
            ConversionDefinition(
                client_id=client_a.id,
                event_name="phone_call",
                conversion_name="Phone Call",
                conversion_type="call",
                active=True,
                is_primary=False,
            ),
        ]
    )
    for m in range(1, 10):
        day = date(2026, m, 15)
        db.add(
            FactGa4Traffic(
                id=uuid.uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url="https://x.test/",
                normalized_url="https://x.test/",
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                sessions=Decimal("1000"),
                active_users=Decimal("800"),
                views=Decimal("1200"),
            )
        )
        db.add(
            FactGa4Event(
                id=uuid.uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url="https://x.test/contact",
                normalized_url="https://x.test/contact",
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                event_name="generate_lead",
                event_count=10,
            )
        )
        db.add(
            FactGa4Event(
                id=uuid.uuid4(),
                client_id=client_a.id,
                date=day,
                raw_url="https://x.test/contact",
                normalized_url="https://x.test/contact",
                session_source="google",
                session_medium="organic",
                channel=OrganicChannel.ORGANIC_SEARCH,
                event_name="phone_call",
                event_count=7,
            )
        )
    db.commit()

    headers = client_header(client_a.id, admin_user.email)
    refused = client.post(
        f"/clients/{client_a.id}/baseline/lock",
        headers=headers,
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
        f"/clients/{client_a.id}/baseline/lock",
        headers=headers,
        json={
            "source": "ga4",
            "regime_start": "2026-02",
            "lead_events": ["generate_lead"],
            "sync_lead_conversions": True,
        },
    )
    assert agreed.status_code == 200, agreed.text
    assert agreed.json()["lead_conversions_changed"]["remove"] == ["phone_call"]
    assert agreed.json()["version"]["monthly_leads"] == 10.0

    db.expire_all()
    call_row = (
        db.query(ConversionDefinition)
        .filter(ConversionDefinition.client_id == client_a.id, ConversionDefinition.event_name == "phone_call")
        .one()
    )
    assert call_row.active is False
    assert call_row.conversion_type == "call"

    ov = client.get(
        "/v2/clients/overview",
        params={"as_of": through.isoformat()},
        headers=auth_header(admin_user.email),
    ).json()
    item = next(r for r in ov["clients"] if r["id"] == str(client_a.id))
    assert item["leads"] == 10

    setup = client.get(f"/clients/{client_a.id}/setup", headers=headers).json()
    leads_step = next(s for s in setup["steps"] if s["key"] == "leads")
    assert leads_step["done"] is True
    assert "1 event marked as leads" in leads_step["detail"]

    series = client.get(f"/clients/{client_a.id}/baseline/series", headers=headers).json()
    assert series["source"]["lead_events"] == ["generate_lead"]
    assert series["baseline"]["monthly_leads"] == 10.0

    pillars = client.get(
        f"/clients/{client_a.id}/baseline/pillars",
        headers=headers,
    ).json()
    assert pillars["leads"]["lead_events"] == ["generate_lead"]


def test_t5_dashboard_and_decision_measurements_parity_with_overview_for_ecommerce_and_call(
    client, db: Session, client_a: Client, client_b: Client, admin_user
):
    as_of = date(2026, 9, 30)
    start = date(2026, 9, 1)
    day = date(2026, 9, 15)

    # client_a: ecommerce (purchase active + engagement ignored + lingering inactive lead)
    client_a.business_model = "ecommerce"
    db.add(
        DataWatermark(
            client_id=client_a.id,
            source="ga4",
            fact_through_date=as_of,
            validation_status=ValidationStatus.PASSED,
        )
    )
    db.add_all(
        [
            ConversionDefinition(
                client_id=client_a.id,
                event_name="purchase",
                conversion_name="Purchase",
                conversion_type="ecommerce",
                active=True,
                is_primary=True,
            ),
            ConversionDefinition(
                client_id=client_a.id,
                event_name="scroll_90",
                conversion_name="Scroll 90",
                conversion_type="engagement",
                active=True,
            ),
        ]
    )
    db.add(
        FactGa4Traffic(
            id=uuid.uuid4(),
            client_id=client_a.id,
            date=day,
            raw_url="https://a.test/",
            normalized_url="https://a.test/",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=Decimal("400"),
            active_users=Decimal("320"),
            views=Decimal("500"),
        )
    )
    db.add(
        FactGa4Event(
            id=uuid.uuid4(),
            client_id=client_a.id,
            date=day,
            raw_url="https://a.test/checkout",
            normalized_url="https://a.test/checkout",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="purchase",
            event_count=20,
        )
    )

    # client_b: lead_gen (phone_call [`call`])
    client_b.business_model = "lead_gen"
    db.add(
        DataWatermark(
            client_id=client_b.id,
            source="ga4",
            fact_through_date=as_of,
            validation_status=ValidationStatus.PASSED,
        )
    )
    db.add(
        ConversionDefinition(
            client_id=client_b.id,
            event_name="phone_call",
            conversion_name="Phone Call",
            conversion_type="call",
            active=True,
        )
    )
    db.add(
        FactGa4Traffic(
            id=uuid.uuid4(),
            client_id=client_b.id,
            date=day,
            raw_url="https://b.test/",
            normalized_url="https://b.test/",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            sessions=Decimal("250"),
            active_users=Decimal("200"),
            views=Decimal("300"),
        )
    )
    db.add(
        FactGa4Event(
            id=uuid.uuid4(),
            client_id=client_b.id,
            date=day,
            raw_url="https://b.test/contact",
            normalized_url="https://b.test/contact",
            session_source="google",
            session_medium="organic",
            channel=OrganicChannel.ORGANIC_SEARCH,
            event_name="phone_call",
            event_count=9,
        )
    )
    db.commit()

    assert dashboard._lead_event_names(db, client_a.id) == ["purchase"]
    assert dashboard._lead_event_names(db, client_b.id) == ["phone_call"]

    dash_a = dashboard.build_dashboard(db, client_a, start, as_of)
    dash_b = dashboard.build_dashboard(db, client_b, start, as_of)
    meas_a = decision_measurements.measure(db, client_a, end=as_of)
    meas_b = decision_measurements.measure(db, client_b, end=as_of)

    ov = client.get(
        "/v2/clients/overview",
        params={"as_of": as_of.isoformat()},
        headers=auth_header(admin_user.email),
    ).json()
    by_id = {r["id"]: r for r in ov["clients"]}

    assert dash_a["conversions"]["leads"]["current"] == 20.0
    assert meas_a["leads"]["count"] == 20.0
    assert by_id[str(client_a.id)]["leads"] == 20

    assert dash_b["conversions"]["leads"]["current"] == 9.0
    assert meas_b["leads"]["count"] == 9.0
    assert by_id[str(client_b.id)]["leads"] == 9


def test_t5_nul_bytes_concurrent_csv_import_noncanonical_ipv4_and_url_variants(
    engine, client, client_a: Client, admin_user
):
    headers = client_header(client_a.id, admin_user.email)

    # NUL byte rejection (422) on watchlist schemas
    kw_nul = client.post(
        "/v2/watchlist/keywords",
        json={"keyword": "bad\x00kw", "bucket_name": "Core"},
        headers=headers,
    )
    assert kw_nul.status_code == 422

    bucket_nul = client.post(
        "/v2/watchlist/buckets",
        json={"name": "bad\x00bucket"},
        headers=headers,
    )
    assert bucket_nul.status_code == 422

    # Clean NUL stripping/skipping in CSV import (never 500)
    csv_nul = "Topic,Keyword,Volume,Notes\nCore,good\x00term,100,note\x00ok\nCore,\x00,50,blank\n"
    imp_nul = client.post("/v2/watchlist/import", json={"csv_text": csv_nul}, headers=headers)
    assert imp_nul.status_code == 200, imp_nul.text
    assert imp_nul.json()["keywords_created"] == 1
    assert len(imp_nul.json()["skipped"]) == 1

    # Concurrent CSV import savepoint safety (never 500)
    previous_override = app.dependency_overrides.get(get_db)

    def thread_safe_get_db():
        with Session(bind=engine) as s:
            yield s

    app.dependency_overrides[get_db] = thread_safe_get_db
    try:
        barrier = threading.Barrier(3)
        race_csv = "Topic,Keyword,Volume\nRace Bucket,race keyword one,300\nRace Bucket,race keyword two,400\n"

        def run_import():
            with TestClient(app, raise_server_exceptions=False) as tc:
                barrier.wait(timeout=5)
                return tc.post("/v2/watchlist/import", json={"csv_text": race_csv}, headers=headers)

        with ThreadPoolExecutor(max_workers=3) as pool:
            res_list = [f.result() for f in [pool.submit(run_import) for _ in range(3)]]
        assert all(r.status_code in (200, 409) for r in res_list), [(r.status_code, r.text) for r in res_list]
    finally:
        if previous_override is not None:
            app.dependency_overrides[get_db] = previous_override
        else:
            app.dependency_overrides.pop(get_db, None)

    # Non-canonical / octal / hex / short IPv4 rejection (422)
    for bad_ip_url in (
        "http://0177.0.0.1/admin",
        "http://0x7f.0.0.1/admin",
        "http://127.1/admin",
        "http://0x7f000001/admin",
        "http://08.0.0.1/admin",
    ):
        assert public_host_or_error(bad_ip_url) is not None
        draft_res = client.post(
            "/v2/optimizer/draft",
            json={"url": bad_ip_url, "kind": "opening", "depth": "quick", "keyword": "test"},
            headers=headers,
        )
        assert draft_res.status_code == 422, (bad_ip_url, draft_res.status_code, draft_res.text)

    # Malformed IPv6 url_variants safe return ([])
    assert url_variants("http://[::1") == []


def test_t5_nul_bytes_rejected_422_across_optimizer_watchlist_content_baseline_and_multicast_ips(
    client, db: Session, client_a: Client, admin_user, monkeypatch
):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-ant-test-key")
    today = date(2026, 10, 28)
    db.add(
        FactGscQueryPage(
            client_id=client_a.id,
            date=today - timedelta(days=2),
            query="slab leak repair",
            raw_url=f"https://{client_a.domain}/slab-leak",
            normalized_url=f"https://{client_a.domain}/slab-leak",
            country="usa",
            device="DESKTOP",
            impressions=Decimal("400"),
            clicks=Decimal("12"),
            ctr=Decimal("0.03"),
            average_position=Decimal("10.0"),
        )
    )
    db.commit()

    headers = client_header(client_a.id, admin_user.email)

    # 1. POST /v2/optimizer/draft: NUL in text & url -> 422
    draft_nul_text = client.post(
        "/v2/optimizer/draft",
        json={
            "url": f"https://{client_a.domain}/p",
            "kind": "opening",
            "depth": "quick",
            "keyword": "seo",
            "text": "hello\x00world",
        },
        headers=headers,
    )
    assert draft_nul_text.status_code == 422, draft_nul_text.text

    draft_nul_url = client.post(
        "/v2/optimizer/draft",
        json={
            "url": f"https://{client_a.domain}/a\x00b",
            "kind": "opening",
            "depth": "quick",
            "keyword": "seo",
        },
        headers=headers,
    )
    assert draft_nul_url.status_code == 422, draft_nul_url.text

    # 2. GET /v2/optimizer/page?url=...\x00... -> 422
    page_nul_url = client.get(
        "/v2/optimizer/page",
        params={"url": f"https://{client_a.domain}/a\x00b"},
        headers=headers,
    )
    assert page_nul_url.status_code == 422, page_nul_url.text

    # 3. GET /v2/watchlist/suggestions?search=a\x00b -> 422 (with real FactGscQueryPage rows)
    sug_nul = client.get(
        "/v2/watchlist/suggestions",
        params={"search": "a\x00b"},
        headers=headers,
    )
    assert sug_nul.status_code == 422, sug_nul.text
    sug_ok = client.get(
        "/v2/watchlist/suggestions",
        params={"search": "slab"},
        headers=headers,
    )
    assert sug_ok.status_code == 200
    assert [s["key"] for s in sug_ok.json()["suggestions"]] == ["slab leak repair"]

    # 4. POST /v2/content/ignore & /restore: NUL in key -> 422
    ignore_nul = client.post(
        "/v2/content/ignore",
        json={"area": "gap", "key": "bad\x00key"},
        headers=headers,
    )
    assert ignore_nul.status_code == 422, ignore_nul.text

    restore_nul = client.post(
        "/v2/content/restore",
        json={"area": "gap", "key": "bad\x00key"},
        headers=headers,
    )
    assert restore_nul.status_code == 422, restore_nul.text

    # 5. GET /v2/content/gaps/brief?term=foo\x00bar + sibling v2_content inputs -> 422
    brief_nul = client.get(
        "/v2/content/gaps/brief",
        params={"term": "foo\x00bar"},
        headers=headers,
    )
    assert brief_nul.status_code == 422, brief_nul.text

    assert client.get("/v2/content/gaps", params={"q": "foo\x00bar"}, headers=headers).status_code == 422
    assert client.get("/v2/content/topics/detail", params={"label": "foo\x00bar"}, headers=headers).status_code == 422
    assert client.get("/v2/content/refreshes", params={"q": "foo\x00bar"}, headers=headers).status_code == 422
    assert (
        client.get(
            "/v2/content/refreshes/page",
            params={"url": f"https://{client_a.domain}/a\x00b"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/v2/content/refreshes/search",
            params={"query": "foo\x00bar"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v2/content/topics/dismiss",
            json={"label": "foo\x00bar"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v2/content/draft",
            json={"kind": "brief", "key": "foo\x00bar", "depth": "quick"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v2/content/calendar",
            json={"kind": "new_page", "title": "bad\x00title", "target": f"https://{client_a.domain}/p"},
            headers=headers,
        ).status_code
        == 422
    )

    # 6. POST /clients/{id}/baseline/lead-conversions & /baseline/lock NUL -> 422
    lc_nul = client.post(
        f"/clients/{client_a.id}/baseline/lead-conversions",
        json={"lead_events": ["bad\x00event"]},
        headers=headers,
    )
    assert lc_nul.status_code == 422, lc_nul.text

    lock_nul_events = client.post(
        f"/clients/{client_a.id}/baseline/lock",
        json={"source": "ga4", "lead_events": ["bad\x00event"]},
        headers=headers,
    )
    assert lock_nul_events.status_code == 422, lock_nul_events.text

    lock_nul_note = client.post(
        f"/clients/{client_a.id}/baseline/lock",
        json={"source": "ga4", "reason_code": "correction", "reason_note": "bad\x00note text"},
        headers=headers,
    )
    assert lock_nul_note.status_code == 422, lock_nul_note.text

    # 7. Multicast IPv4 and IPv6 rejection (422)
    for mcast_url in (
        "http://224.0.0.1/admin",
        "http://[ff02::1]/admin",
        "http://[ff0e::1]/admin",
        "http://[::ffff:224.0.0.1]/admin",
    ):
        assert public_host_or_error(mcast_url) is not None, mcast_url
        assert (
            client.get("/v2/optimizer/page", params={"url": mcast_url}, headers=headers).status_code
            == 422
        ), mcast_url
        assert (
            client.post(
                "/v2/optimizer/draft",
                json={"url": mcast_url, "kind": "opening", "depth": "quick", "keyword": "test"},
                headers=headers,
            ).status_code
            == 422
        ), mcast_url
