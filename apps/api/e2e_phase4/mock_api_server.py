"""Ephemeral API server and browser-E2E DB seeder for Phase 4 full-stack tests.

Usage:
    python -m e2e_phase4.mock_api_server --port 8001 --seed-browser-suite
    python -m e2e_phase4.mock_api_server --seed-browser-suite --seed-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# Configure test environment BEFORE importing `app.*` or `e2e_phase4.conftest`.
_DEFAULT_DB_URL = "postgresql+psycopg://ryanshelley@localhost:5432/organiciq_test_e2e_phase4"
_DB_URL = (
    os.environ.get("TEST_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or _DEFAULT_DB_URL
)
if "organiciq_test" not in _DB_URL:
    raise RuntimeError(
        f"Refusing to run mock_api_server against non-test DB URL: {_DB_URL}"
    )

os.environ["APP_ENV"] = "test"
os.environ["TEST_DATABASE_URL"] = _DB_URL
os.environ["DATABASE_URL"] = _DB_URL
os.environ.setdefault("AUTH_SECRET", "test-auth-secret-for-the-suite-only-0123456789")
os.environ["ANTHROPIC_API_KEY"] = "e2e-stub-key"
os.environ.setdefault("SE_RANKING_API_KEY", "test-se-ranking-key")
os.environ.setdefault("SMA_ADMIN_EMAILS", "admin@smamarketing.com")

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.db import Base  # noqa: E402
from app.core.settings import get_settings  # noqa: E402

get_settings.cache_clear()
_SETTINGS = get_settings()

from app.models.client import ClientStatus  # noqa: E402
from app.models.config import OrganicChannel  # noqa: E402
from app.models.integration import ConnectionStatus, IntegrationProvider  # noqa: E402
from app.models.user import UserRole  # noqa: E402
from e2e_phase4.conftest import (  # noqa: E402
    _ensure_named_test_database,
    _shift_month,
    fake_llm_call,
    make_client,
    make_tier,
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
    seed_watermark,
    set_integration,
)


def install_inprocess_stubs() -> None:
    """Patch external HTTP and LLM boundaries inside the running uvicorn process."""
    from app.integrations import teamwork
    from app.schema_tools import llm
    from app.services import google_updates, page_diagnostic

    get_settings().anthropic_api_key = "e2e-stub-key"
    llm.call = fake_llm_call

    def _refuse_get(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("no external network calls in E2E server")

    async def _refuse_fetch(*_args: Any, **_kwargs: Any) -> Any:
        raise httpx.ConnectError("no external network calls in E2E server")

    google_updates.httpx.get = _refuse_get
    page_diagnostic._fetch = _refuse_fetch
    teamwork.create_subtask = lambda **kw: {
        "id": f"sub-{str(kw.get('name', 'task'))[:12]}",
        "url": "",
    }


def reset_and_seed_browser_suite() -> dict[str, Any]:
    """Reset the E2E DB schema and seed multi-tenant Phase 4 browser fixtures."""
    url = _ensure_named_test_database(_SETTINGS.database_url)
    eng = create_engine(url, pool_pre_ping=True)
    Base.metadata.drop_all(bind=eng)
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_sync_jobs_active_client_source
                ON sync_jobs (client_id, source)
                WHERE status IN ('queued', 'fetching', 'staging', 'normalizing', 'validating')
                """
            )
        )

    SessionLocal = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    db = SessionLocal()
    try:
        today = date.today()
        recent_1 = today - timedelta(days=3)
        recent_2 = today - timedelta(days=10)
        prior_1 = today - timedelta(days=38)

        tier = make_tier(
            db,
            name="Launch",
            tracked_keyword_limit=100,
            tracked_prompt_limit=50,
            content_allowance=4,
            update_allowance=4,
            growth_action_allowance=2,
            conversion_limit=5,
            reporting_level="launch",
        )

        # ── Clients ───────────────────────────────────────────────────────────
        alpha = make_client(
            db,
            tier,
            "Acme Plumbing",
            domain="acmeplumbing.example",
            status=ClientStatus.ACTIVE,
            service_mode="execution",
            brand_aliases=["acme plumbing", "acme"],
            competitor_domains=["rivalplumbing.example"],
            sitemap_url="https://acmeplumbing.example/sitemap.xml",
            monthly_lead_goal=25,
            business_model="lead_gen",
            service_reporting={"organiciq": True, "ad_accelerator": False},
        )
        beta = make_client(
            db,
            tier,
            "Beacon Dental",
            domain="beacondental.example",
            status=ClientStatus.ACTIVE,
            service_mode="execution",
            brand_aliases=["beacon dental", "beacon"],
            competitor_domains=["otherdental.example"],
            sitemap_url="https://beacondental.example/sitemap.xml",
            monthly_lead_goal=40,
            business_model="lead_gen",
            service_reporting={"organiciq": True, "ad_accelerator": False},
        )
        gamma = make_client(
            db,
            tier,
            "Cedar Consulting Null",
            domain="cedarconsulting.example",
            status=ClientStatus.ONBOARDING,
            service_mode="consulting",
            business_model="lead_gen",
            service_reporting={"organiciq": True, "ad_accelerator": False},
        )

        # ── Users ─────────────────────────────────────────────────────────────
        admin = make_user(db, email="admin@smamarketing.com", role=UserRole.SMA_ADMIN, name="Admin")
        team = make_user(
            db,
            email="team@smamarketing.com",
            role=UserRole.SMA_TEAM,
            name="Team Member",
            assign_clients=[alpha],
        )
        viewer = make_user(
            db,
            email="viewer@acme-plumbing.example",
            role=UserRole.CLIENT_VIEWER,
            name="Client Viewer",
            assign_clients=[alpha],
        )

        # ── Client Alpha rich fixtures ────────────────────────────────────────
        set_integration(db, alpha, IntegrationProvider.GA4, "properties/111111")
        set_integration(db, alpha, IntegrationProvider.GSC, "sc-domain:acmeplumbing.example")
        set_integration(db, alpha, IntegrationProvider.SE_RANKING, "proj-alpha-1")

        seed_conversion_def(db, alpha, "generate_lead", conversion_type="lead", active=True, is_primary=True)
        seed_conversion_def(db, alpha, "page_engagement", conversion_type="engagement", active=True, is_primary=False)
        seed_lead_exclusion(
            db,
            alpha,
            url_pattern="https://acmeplumbing.example/test-form*",
            reason="Internal QA test form submissions",
        )

        seed_ga4_baseline_window(
            db,
            alpha,
            months=7,
            sessions_per_month=1200,
            direct_sessions_per_month=400,
            leads_per_month=18,
            event_name="generate_lead",
            include_partial_last_month=True,
        )

        # Recent 30d & prior 30d traffic/events on distinct service URLs for Overview
        seed_ga4_traffic(db, alpha, recent_1, 650, channel=OrganicChannel.ORGANIC_SEARCH, url="/services/item-1")
        seed_ga4_traffic(db, alpha, recent_2, 550, channel=OrganicChannel.DIRECT_UNATTRIBUTED, url="/services/item-2")
        seed_ga4_traffic(db, alpha, prior_1, 900, channel=OrganicChannel.ORGANIC_SEARCH, url="/services/item-1")
        seed_ga4_event(db, alpha, recent_1, "generate_lead", 14, channel=OrganicChannel.ORGANIC_SEARCH, url="/services/item-1")
        seed_ga4_event(db, alpha, recent_1, "generate_lead", 5, channel=OrganicChannel.ORGANIC_SEARCH, url="/test-form")
        seed_ga4_event(db, alpha, prior_1, "generate_lead", 12, channel=OrganicChannel.ORGANIC_SEARCH, url="/services/item-1")

        # GSC daily, page, and query-page facts
        seed_gsc_daily(db, alpha, recent_1, impressions=2200, clicks=110, position=9.4)
        seed_gsc_daily(db, alpha, recent_2, impressions=1800, clicks=90, position=10.2)
        seed_gsc_daily(db, alpha, prior_1, impressions=3200, clicks=150, position=11.0)
        seed_gsc_page(db, alpha, recent_1, "/services/item-1", impressions=2200, clicks=110, position=9.4)
        seed_gsc_page(db, alpha, recent_2, "/services/item-2", impressions=1800, clicks=90, position=10.2)
        seed_watermark(db, alpha, "gsc_pages", recent_1)

        # GSC suggestions (untracked non-brand) + brand + gap candidates + irrelevant noise
        seed_gsc_query_page(db, alpha, recent_1, "tankless water heater repair", 640, 8.4, clicks=22, url="/services/item-1")
        seed_gsc_query_page(db, alpha, recent_1, "emergency drain cleaning", 520, 9.1, clicks=18, url="/services/item-2")
        seed_gsc_query_page(db, alpha, recent_1, "trenchless sewer replacement", 410, 11.3, clicks=12, url="/services/item-3")
        seed_gsc_query_page(db, alpha, recent_1, "acme plumbing near me", 900, 1.4, clicks=140, url="/")
        seed_gsc_query_page(db, alpha, recent_1, "hydro jetting sewer line", 450, 14.2, clicks=5, url="/services/item-1")
        seed_gsc_query_page(db, alpha, recent_1, "login", 210, 15.0, clicks=10, url="/services/item-1")
        seed_gsc_query_page(db, alpha, recent_1, "careers", 190, 16.0, clicks=4, url="/services/item-1")
        seed_gsc_query_page(db, alpha, recent_1, "ac", 180, 17.0, clicks=3, url="/services/item-1")
        seed_gsc_query_page(db, alpha, recent_1, "rivalplumbing pricing", 240, 18.0, clicks=2, url="/services/item-1")

        # Watchlist buckets & keywords
        bucket_core = seed_bucket(db, alpha, "Core Services", sort_order=0)
        bucket_drain = seed_bucket(db, alpha, "Local Drain", sort_order=1)
        seed_kw(db, bucket_core, alpha, "water heater repair", volume=1900, difficulty=42, intent="commercial")
        seed_kw(db, bucket_core, alpha, "drain cleaning", volume=2400, difficulty=38, intent="commercial")
        seed_kw(db, bucket_drain, alpha, "sewer line inspection", volume=880, difficulty=31, intent="informational")

        # Crawl pages (>=10 indexable) + unranked optimizer target URL
        crawl_urls = seed_indexable_site(db, alpha, count=12, snap_date=recent_1)
        unranked_url = seed_crawl_page(
            db,
            alpha,
            f"https://{alpha.domain}",
            "/services/trenchless-sewer",
            recent_1,
            title="Trenchless Sewer Repair Services",
            desc="No-dig sewer repair, copper repiping, and plumbing pipe relining.",
            sections=[
                {
                    "level": 1,
                    "heading": "Trenchless Sewer Repair",
                    "first_paragraph": (
                        "Acme Plumbing repairs damaged underground sewer lines without digging up your yard. "
                        "Our licensed technicians inspect pipes by camera and restore flow the same day."
                    ),
                }
            ],
            page_type="service",
        )

        # Priced content gaps & excluded watch target (seeded as GSC + SER candidate so exclusion is non-vacuous)
        seed_ser_metric(db, alpha, "hydro jetting sewer line", volume=720, difficulty=28)
        seed_competitor_kw(db, alpha, "rivalplumbing.example", "copper repiping cost", 3.2, recent_1, volume=590, difficulty=35)
        seed_ser_metric(db, alpha, "copper repiping cost", volume=590, difficulty=35)
        seed_gsc_query_page(db, alpha, recent_1, "free plumbing sticker", 310, 14.0, clicks=1, url="/services/item-1")
        seed_ser_metric(db, alpha, "free plumbing sticker", volume=400, difficulty=15)
        seed_watch_target_excluded(db, alpha, "free plumbing sticker")
        db.commit()

        # ── Client Beta fixtures (higher metrics for sorting contrast) ─────────
        set_integration(db, beta, IntegrationProvider.GA4, "properties/222222")
        set_integration(db, beta, IntegrationProvider.GSC, "sc-domain:beacondental.example")
        seed_conversion_def(db, beta, "book_appointment", conversion_type="lead", active=True, is_primary=True)
        seed_conversion_def(db, beta, "purchase", conversion_type="ecommerce", active=True, is_primary=False)
        seed_ga4_baseline_window(
            db,
            beta,
            months=7,
            sessions_per_month=2400,
            direct_sessions_per_month=600,
            leads_per_month=35,
            event_name="book_appointment",
            include_partial_last_month=False,
        )
        seed_ga4_traffic(db, beta, recent_1, 2100, channel=OrganicChannel.ORGANIC_SEARCH, url="/services/item-1")
        seed_ga4_traffic(db, beta, recent_2, 700, channel=OrganicChannel.DIRECT_UNATTRIBUTED, url="/services/item-2")
        seed_ga4_event(db, beta, recent_1, "book_appointment", 32, channel=OrganicChannel.ORGANIC_SEARCH, url="/services/item-1")
        for m in range(1, 8):
            m_day = _shift_month(today.replace(day=1), -m).replace(day=15)
            seed_ga4_event(db, beta, m_day, "purchase", 20, channel=OrganicChannel.ORGANIC_SEARCH, url="/checkout")
        seed_gsc_daily(db, beta, recent_1, impressions=6500, clicks=340, position=5.8)
        seed_gsc_daily(db, beta, prior_1, impressions=5200, clicks=260, position=6.9)
        seed_gsc_page(db, beta, recent_1, "/services/item-1", impressions=6500, clicks=340, position=5.8)
        seed_watermark(db, beta, "gsc_pages", recent_1)
        seed_indexable_site(db, beta, count=12, snap_date=recent_1)
        bucket_beta = seed_bucket(db, beta, "Preventive Care", sort_order=0)
        seed_kw(db, bucket_beta, beta, "teeth cleaning", volume=1600, difficulty=30, intent="commercial")
        db.commit()

        manifest: dict[str, Any] = {
            "database_url": _SETTINGS.database_url,
            "tier_id": str(tier.id),
            "users": {
                "admin": {"id": str(admin.id), "email": admin.email, "role": admin.role.value},
                "team": {"id": str(team.id), "email": team.email, "role": team.role.value},
                "viewer": {"id": str(viewer.id), "email": viewer.email, "role": viewer.role.value},
            },
            "clients": {
                "alpha": {
                    "id": str(alpha.id),
                    "slug": alpha.slug,
                    "name": alpha.client_name,
                    "domain": alpha.domain,
                    "service_mode": alpha.service_mode,
                    "unranked_optimizer_url": unranked_url,
                    "crawl_sample_url": crawl_urls[0],
                    "buckets": {
                        "core": str(bucket_core.id),
                        "drain": str(bucket_drain.id),
                    },
                },
                "beta": {
                    "id": str(beta.id),
                    "slug": beta.slug,
                    "name": beta.client_name,
                    "domain": beta.domain,
                    "service_mode": beta.service_mode,
                },
                "gamma": {
                    "id": str(gamma.id),
                    "slug": gamma.slug,
                    "name": gamma.client_name,
                    "domain": gamma.domain,
                    "service_mode": gamma.service_mode,
                },
            },
        }
        return manifest
    finally:
        db.close()
        eng.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4 E2E Mock API Server & Seeder")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--seed-browser-suite", action="store_true")
    parser.add_argument("--seed-only", action="store_true")
    parser.add_argument("--seed-manifest", type=Path, default=None)
    args = parser.parse_args(argv)

    install_inprocess_stubs()

    if args.seed_browser_suite:
        manifest = reset_and_seed_browser_suite()
        payload = json.dumps(manifest, indent=2)
        if args.seed_manifest is not None:
            args.seed_manifest.parent.mkdir(parents=True, exist_ok=True)
            args.seed_manifest.write_text(payload + "\n", encoding="utf-8")
        print(payload, flush=True)

    if args.seed_only:
        return 0

    import app.main  # noqa: E402

    print(
        f"Starting mock_api_server on http://{args.host}:{args.port} (db={_SETTINGS.database_url})",
        file=sys.stderr,
        flush=True,
    )
    uvicorn.run(
        app.main.app,
        host=args.host,
        port=args.port,
        workers=1,
        reload=False,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
