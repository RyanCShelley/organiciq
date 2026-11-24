"""Isolated E2E test harness for Organic IQ Phase 4 (`organiciq_test_e2e_phase4`).

Shadows root `tests/conftest.py:engine` so `TEST_DATABASE_URL` defaults to
`organiciq_test_e2e_phase4` and auto-creates/tears down that isolated DB
without touching `organiciq_test` or `organiciq_test_e2e`.

Opaque-box rule: imports ONLY stable ORM models, core DB/test helpers,
and external network/LLM boundaries — never M1–M6 feature service internals.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable

# Must precede any `app.*` or `tests.conftest` import so `app.core.db.engine` and
# `app.core.db.SessionLocal` bind deterministically to `organiciq_test_e2e_phase4`
# instead of `.env`'s `DATABASE_URL`.
DEFAULT_E2E_DB_URL = "postgresql+psycopg://ryanshelley@localhost:5432/organiciq_test_e2e_phase4"
os.environ["APP_ENV"] = "test"
_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL") or DEFAULT_E2E_DB_URL
if "organiciq_test" not in _TEST_DB_URL:
    raise RuntimeError(f"Refusing to run E2E suite against non-test DB URL: {_TEST_DB_URL}")
os.environ["TEST_DATABASE_URL"] = _TEST_DB_URL
os.environ["DATABASE_URL"] = _TEST_DB_URL

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.settings import get_settings  # noqa: E402

get_settings.cache_clear()

from tests.conftest import (  # noqa: E402, F401
    _fresh_result_caches,
    _no_real_teamwork_subtasks,
    admin_user,
    auth_header,
    client,
    client_a,
    client_b,
    client_header,
    db,
    settings,
    team_user,
    tier,
)

from app.core.db import Base  # noqa: E402
from app.models.client import Client, ClientStatus, Tier  # noqa: E402
from app.models.config import ConversionDefinition, LeadExclusion, OrganicChannel  # noqa: E402
from app.models.consulting import ConsultingProfile, ConsultingReport  # noqa: E402
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot  # noqa: E402
from app.models.decision import MonthlyRecord  # noqa: E402
from app.models.ga4 import FactGa4Event, FactGa4Traffic  # noqa: E402
from app.models.gsc import FactGscDaily, FactGscPage, FactGscQueryPage  # noqa: E402
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider  # noqa: E402
from app.models.job import DataWatermark, ValidationStatus  # noqa: E402
from app.models.seranking import (  # noqa: E402
    FactSerCompetitorKeyword,
    FactSerKeyword,
    FactSerKeywordMetric,
)
from app.models.user import User, UserClient, UserRole  # noqa: E402
from app.models.watch_target import WatchTarget  # noqa: E402
from app.models.watchlist import WatchlistBucket, WatchlistKeyword  # noqa: E402
from app.services import google_updates, page_diagnostic  # noqa: E402


def _ensure_named_test_database(url: str) -> str:
    """Ensure the test database named in `url` exists without touching other DBs."""
    if "organiciq_test" not in url:
        raise RuntimeError(f"Refusing to run E2E suite against non-test DB URL: {url}")
    db_name = url.split("?", 1)[0].rsplit("/", 1)[-1]
    if not re.fullmatch(r"[A-Za-z0-9_]+", db_name) or "organiciq_test" not in db_name:
        raise RuntimeError(f"Unsafe test database name: {db_name!r}")

    base, _, query = url.partition("?")
    admin_url = base.rsplit("/", 1)[0] + "/postgres" + (f"?{query}" if query else "")
    admin_eng = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_eng.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        admin_eng.dispose()
    return url


@pytest.fixture(scope="session")
def engine():
    """Shadow `tests/conftest.py:engine` for isolated `organiciq_test_e2e_phase4` runs."""
    url = _ensure_named_test_database(settings.database_url)
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
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture(autouse=True)
def _no_external_network(monkeypatch):
    """Block outbound HTTP calls to Google status feeds or live client pages."""

    def _refuse_get(*_args, **_kwargs):
        raise RuntimeError("no external network calls in E2E tests")

    async def _refuse_fetch(*_args, **_kwargs):
        raise httpx.ConnectError("no external network calls in E2E tests")

    monkeypatch.setattr(google_updates.httpx, "get", _refuse_get)
    monkeypatch.setattr(page_diagnostic, "_fetch", _refuse_fetch)


# ── Auth & HTTP header helpers ────────────────────────────────────────────────


def admin_headers(client_obj: Client) -> dict[str, str]:
    return client_header(client_obj.id, "admin@smamarketing.com")


def api_headers(
    client_id: uuid.UUID | None = None,
    email: str | None = None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if email is not None:
        headers.update(auth_header(email))
    if client_id is not None:
        headers["X-OrganicIQ-Client-Id"] = str(client_id)
    return headers


def make_user(
    db: Session,
    *,
    email: str,
    role: UserRole,
    assign_clients: Iterable[Client] = (),
    name: str | None = None,
    is_active: bool = True,
) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email.lower(),
        name=name or email.split("@", 1)[0],
        google_sub=f"sub-{uuid.uuid4().hex[:10]}",
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    for c in assign_clients:
        db.add(UserClient(user_id=user.id, client_id=c.id, role=role))
    db.commit()
    db.refresh(user)
    return user


# ── Clients & Tiers ───────────────────────────────────────────────────────────


def make_tier(
    db: Session,
    name: str | None = None,
    *,
    tracked_keyword_limit: int = 100,
    tracked_prompt_limit: int = 50,
    content_allowance: int = 3,
    update_allowance: int = 3,
    growth_action_allowance: int = 1,
    conversion_limit: int = 5,
    reporting_level: str = "launch",
) -> Tier:
    row = Tier(
        id=uuid.uuid4(),
        tier_name=name or f"Tier-{uuid.uuid4().hex[:8]}",
        tracked_keyword_limit=tracked_keyword_limit,
        tracked_prompt_limit=tracked_prompt_limit,
        content_allowance=content_allowance,
        update_allowance=update_allowance,
        growth_action_allowance=growth_action_allowance,
        conversion_limit=conversion_limit,
        reporting_level=reporting_level,
        watchlist_cadence="monthly",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def make_client(
    db: Session,
    tier: Tier,
    name: str,
    *,
    domain: str | None = None,
    status: ClientStatus = ClientStatus.ACTIVE,
    service_mode: str = "execution",
    brand_aliases: list[str] | None = None,
    competitor_domains: list[str] | None = None,
    sitemap_url: str | None = None,
    monthly_lead_goal: int | None = None,
    business_model: str | None = None,
    service_reporting: dict[str, Any] | None = None,
    style_notes: str | None = None,
) -> Client:
    slug_base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "client"
    c = Client(
        id=uuid.uuid4(),
        client_name=name,
        slug=f"{slug_base}-{uuid.uuid4().hex[:6]}",
        domain=domain or f"{slug_base.replace('-', '')}.example",
        tier_id=tier.id,
        status=status,
        service_mode=service_mode,
        timezone="America/New_York",
        brand_aliases=brand_aliases if brand_aliases is not None else [],
        competitor_domains=competitor_domains if competitor_domains is not None else [],
        sitemap_url=sitemap_url,
        monthly_lead_goal=monthly_lead_goal,
        business_model=business_model,
        service_reporting=service_reporting,
        style_notes=style_notes,
    )
    db.add(c)
    db.flush()
    for provider in IntegrationProvider:
        db.add(
            Integration(
                client_id=c.id,
                provider=provider,
                connection_status=ConnectionStatus.NOT_CONNECTED,
            )
        )
    db.commit()
    db.refresh(c)
    return c


# ── Integration & Setup helpers ───────────────────────────────────────────────


def set_integration(
    db: Session,
    client_obj: Client,
    provider: IntegrationProvider | str,
    external_property_id: str | None,
    status: ConnectionStatus = ConnectionStatus.CONNECTED,
    *,
    external_account_id: str | None = None,
) -> Integration:
    prov = provider if isinstance(provider, IntegrationProvider) else IntegrationProvider(provider)
    row = (
        db.query(Integration)
        .filter(Integration.client_id == client_obj.id, Integration.provider == prov)
        .one_or_none()
    )
    if row is None:
        row = Integration(
            client_id=client_obj.id,
            provider=prov,
            external_property_id=external_property_id,
            external_account_id=external_account_id,
            connection_status=status,
        )
        db.add(row)
    else:
        row.external_property_id = external_property_id
        if external_account_id is not None:
            row.external_account_id = external_account_id
        row.connection_status = status
    db.commit()
    db.refresh(row)
    return row


def seed_conversion_def(
    db: Session,
    client_obj: Client,
    event_name: str = "generate_lead",
    *,
    conversion_name: str | None = None,
    conversion_type: str = "lead",
    active: bool = True,
    is_primary: bool = True,
) -> ConversionDefinition:
    row = ConversionDefinition(
        id=uuid.uuid4(),
        client_id=client_obj.id,
        event_name=event_name,
        conversion_name=conversion_name or event_name.replace("_", " ").title(),
        conversion_type=conversion_type,
        is_primary=is_primary,
        active=active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def seed_lead_exclusion(
    db: Session,
    client_obj: Client,
    *,
    reason: str = "spam",
    url_pattern: str | None = None,
    event_name: str | None = None,
    session_source: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> LeadExclusion:
    row = LeadExclusion(
        id=uuid.uuid4(),
        client_id=client_obj.id,
        reason=reason,
        url_pattern=url_pattern,
        event_name=event_name,
        session_source=session_source,
        date_from=date_from,
        date_to=date_to,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def seed_watermark(
    db: Session,
    client_obj: Client,
    source: str,
    fact_through_date: date,
    *,
    validation_status: ValidationStatus = ValidationStatus.PASSED,
) -> DataWatermark:
    row = (
        db.query(DataWatermark)
        .filter(DataWatermark.client_id == client_obj.id, DataWatermark.source == source)
        .one_or_none()
    )
    if row is None:
        row = DataWatermark(
            id=uuid.uuid4(),
            client_id=client_obj.id,
            source=source,
            fact_through_date=fact_through_date,
            validation_status=validation_status,
        )
        db.add(row)
    else:
        row.fact_through_date = fact_through_date
        row.validation_status = validation_status
    db.commit()
    db.refresh(row)
    return row


# ── GA4 & GSC Traffic / Visibility / Events helpers ───────────────────────────


def _full_url(client_obj: Client, url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    path = url if url.startswith("/") else f"/{url}"
    return f"https://{client_obj.domain}{path}"


def seed_ga4_traffic(
    db: Session,
    client_obj: Client,
    day: date,
    sessions: int | float,
    *,
    channel: OrganicChannel = OrganicChannel.ORGANIC_SEARCH,
    url: str = "/",
    active_users: int | float | None = None,
    views: int | float | None = None,
    engaged_sessions: int | float | None = None,
    session_source: str = "",
    session_medium: str = "",
) -> FactGa4Traffic:
    full = _full_url(client_obj, url)
    row = FactGa4Traffic(
        id=uuid.uuid4(),
        client_id=client_obj.id,
        date=day,
        raw_url=full,
        normalized_url=full,
        session_source=session_source,
        session_medium=session_medium,
        channel=channel,
        sessions=Decimal(str(sessions)),
        active_users=Decimal(str(int(sessions * 0.8) if active_users is None else active_users)),
        views=Decimal(str(int(sessions * 1.3) if views is None else views)),
        engaged_sessions=(
            None if engaged_sessions is None else Decimal(str(engaged_sessions))
        ),
    )
    db.add(row)
    return row


def seed_ga4_event(
    db: Session,
    client_obj: Client,
    day: date,
    event_name: str,
    event_count: int,
    *,
    channel: OrganicChannel = OrganicChannel.ORGANIC_SEARCH,
    url: str = "/",
    session_source: str = "",
    session_medium: str = "",
) -> FactGa4Event:
    full = _full_url(client_obj, url)
    row = FactGa4Event(
        id=uuid.uuid4(),
        client_id=client_obj.id,
        date=day,
        raw_url=full,
        normalized_url=full,
        session_source=session_source,
        session_medium=session_medium,
        channel=channel,
        event_name=event_name,
        event_count=int(event_count),
    )
    db.add(row)
    return row


def _shift_month(first_of_month: date, delta_months: int) -> date:
    total = first_of_month.year * 12 + (first_of_month.month - 1) + delta_months
    year, month = divmod(total, 12)
    return date(year, month + 1, 1)


def _month_end(first_of_month: date) -> date:
    return _shift_month(first_of_month, 1) - timedelta(days=1)


def seed_ga4_baseline_window(
    db: Session,
    client_obj: Client,
    *,
    months: int = 7,
    end_month_day: date | None = None,
    sessions_per_month: int = 1000,
    direct_sessions_per_month: int = 400,
    leads_per_month: int = 10,
    event_name: str = "generate_lead",
    include_partial_last_month: bool = False,
) -> date:
    """Seed `months` complete GA4 calendar months starting on day 1 of the earliest month.

    Ensures an active `ConversionDefinition` and `DataWatermark(source="ga4")` exist so
    `GET /clients/{id}/baseline/series` and `POST /clients/{id}/baseline/lock` succeed.
    When `include_partial_last_month=True`, seeds an extra partial month at the end so
    `partial_month_dropped` info flag is emitted while retaining all `months` complete months.
    """
    existing_def = (
        db.query(ConversionDefinition)
        .filter(
            ConversionDefinition.client_id == client_obj.id,
            ConversionDefinition.event_name == event_name,
            ConversionDefinition.active.is_(True),
        )
        .first()
    )
    if existing_def is None:
        seed_conversion_def(db, client_obj, event_name=event_name, conversion_type="lead", active=True, is_primary=True)

    if end_month_day is None:
        last_complete_first = _shift_month(date.today().replace(day=1), -1)
    else:
        month_first = end_month_day.replace(day=1)
        if include_partial_last_month and end_month_day < _month_end(month_first):
            last_complete_first = _shift_month(month_first, -1)
        else:
            last_complete_first = month_first

    complete_starts = [_shift_month(last_complete_first, -i) for i in range(months - 1, -1, -1)]
    for month_day in complete_starts:
        seed_ga4_traffic(db, client_obj, month_day, sessions_per_month, channel=OrganicChannel.ORGANIC_SEARCH, url="/")
        if direct_sessions_per_month > 0:
            seed_ga4_traffic(
                db,
                client_obj,
                month_day,
                direct_sessions_per_month,
                channel=OrganicChannel.DIRECT_UNATTRIBUTED,
                url="/",
            )
        if leads_per_month > 0:
            seed_ga4_event(db, client_obj, month_day, event_name, leads_per_month, channel=OrganicChannel.ORGANIC_SEARCH, url="/")

    if include_partial_last_month:
        if end_month_day is not None and end_month_day < _month_end(end_month_day.replace(day=1)):
            partial_first = end_month_day.replace(day=1)
            through = end_month_day
        else:
            partial_first = _shift_month(last_complete_first, 1)
            through = partial_first + timedelta(days=11)
        seed_ga4_traffic(db, client_obj, partial_first, max(100, sessions_per_month // 3), channel=OrganicChannel.ORGANIC_SEARCH, url="/")
        if direct_sessions_per_month > 0:
            seed_ga4_traffic(
                db,
                client_obj,
                partial_first,
                max(40, direct_sessions_per_month // 3),
                channel=OrganicChannel.DIRECT_UNATTRIBUTED,
                url="/",
            )
        if leads_per_month > 0:
            seed_ga4_event(
                db,
                client_obj,
                partial_first,
                event_name,
                max(1, leads_per_month // 3),
                channel=OrganicChannel.ORGANIC_SEARCH,
                url="/",
            )
    else:
        through = _month_end(last_complete_first)

    seed_watermark(db, client_obj, "ga4", through)
    db.commit()
    return through


def seed_gsc_daily(
    db: Session,
    client_obj: Client,
    day: date,
    impressions: int,
    clicks: int,
    *,
    position: float = 10.0,
    gsc_site_url: str = "",
) -> FactGscDaily:
    ctr = Decimal(clicks) / Decimal(impressions) if impressions > 0 else Decimal(0)
    row = FactGscDaily(
        id=uuid.uuid4(),
        client_id=client_obj.id,
        gsc_site_url=gsc_site_url,
        date=day,
        impressions=Decimal(impressions),
        clicks=Decimal(clicks),
        ctr=ctr,
        average_position=Decimal(str(position)),
    )
    db.add(row)
    return row


def seed_gsc_page(
    db: Session,
    client_obj: Client,
    day: date,
    url: str,
    impressions: int,
    clicks: int,
    *,
    position: float = 10.0,
    country: str = "",
    device: str = "",
    gsc_site_url: str = "",
) -> FactGscPage:
    full = _full_url(client_obj, url)
    ctr = Decimal(clicks) / Decimal(impressions) if impressions > 0 else Decimal(0)
    row = FactGscPage(
        id=uuid.uuid4(),
        client_id=client_obj.id,
        gsc_site_url=gsc_site_url,
        date=day,
        raw_url=full,
        normalized_url=full,
        country=country,
        device=device,
        impressions=Decimal(impressions),
        clicks=Decimal(clicks),
        ctr=ctr,
        average_position=Decimal(str(position)),
    )
    db.add(row)
    return row


def seed_gsc_query_page(
    db: Session,
    client_obj: Client,
    day: date,
    query: str,
    impressions: int,
    position: float,
    *,
    clicks: int = 1,
    url: str | None = None,
    country: str = "usa",
    device: str = "DESKTOP",
    gsc_site_url: str = "",
) -> FactGscQueryPage:
    full = _full_url(client_obj, url or "/page")
    ctr = Decimal(clicks) / Decimal(impressions) if impressions > 0 else Decimal(0)
    row = FactGscQueryPage(
        id=uuid.uuid4(),
        client_id=client_obj.id,
        gsc_site_url=gsc_site_url,
        date=day,
        query=query,
        raw_url=full,
        normalized_url=full,
        country=country,
        device=device,
        impressions=Decimal(impressions),
        clicks=Decimal(clicks),
        ctr=ctr,
        average_position=Decimal(str(position)),
    )
    db.add(row)
    return row


# ── Watchlist, Crawl, SERP & Content helpers ──────────────────────────────────


def norm_key(value: str) -> str:
    return " ".join(value.strip().lower().split())


def seed_bucket(
    db: Session,
    client_obj: Client,
    name: str,
    *,
    sort_order: int = 0,
) -> WatchlistBucket:
    bucket = WatchlistBucket(
        client_id=client_obj.id,
        name=name,
        name_key=norm_key(name),
        sort_order=sort_order,
    )
    db.add(bucket)
    db.flush()
    return bucket


def seed_kw(
    db: Session,
    bucket: WatchlistBucket,
    client_obj: Client,
    keyword: str,
    *,
    volume: int | None = None,
    difficulty: int | None = None,
    intent: str | None = None,
    paired_ai_prompt: str | None = None,
    notes: str | None = None,
    source: str = "csv",
) -> WatchlistKeyword:
    kw = WatchlistKeyword(
        client_id=client_obj.id,
        bucket_id=bucket.id,
        keyword=keyword,
        keyword_key=norm_key(keyword),
        volume=volume,
        difficulty=difficulty,
        intent=intent,
        paired_ai_prompt=paired_ai_prompt,
        notes=notes,
        source=source,
    )
    db.add(kw)
    db.flush()
    return kw


def seed_crawl_page(
    db: Session,
    client_obj: Client,
    base_url: str,
    path: str,
    snap_date: date,
    *,
    status: int = 200,
    title: str | None = "Default Unique Title",
    desc: str | None = "Default unique meta description.",
    indexable: bool = True,
    dup_title: bool = False,
    dup_desc: bool = False,
    redirects: int = 0,
    soft_404: bool = False,
    blocked_by_robots: bool = False,
    canonical_url: str | None = None,
    word_count: int = 600,
    in_sitemap: bool = True,
    inbound_internal_links: int = 3,
    sections: list[dict[str, Any]] | None = None,
    page_type: str | None = None,
    source: str = CRAWL_SOURCE_FIRST_PARTY,
) -> str:
    url = f"{base_url.rstrip('/')}{path}"
    db.add(
        FactCrawlPageSnapshot(
            client_id=client_obj.id,
            source=source,
            snapshot_date=snap_date,
            raw_url=url,
            normalized_url=url,
            status_code=status,
            indexable=indexable,
            title=title,
            description=desc,
            title_duplicate=dup_title,
            description_duplicate=dup_desc,
            redirect_count=redirects,
            soft_404=soft_404,
            blocked_by_robots=blocked_by_robots,
            canonical_url=canonical_url,
            word_count=word_count,
            in_sitemap=in_sitemap,
            inbound_internal_links=inbound_internal_links,
            sections=sections,
            page_type=page_type,
        )
    )
    return url


def seed_indexable_site(
    db: Session,
    client_obj: Client,
    count: int = 12,
    *,
    snap_date: date | None = None,
    base_url: str | None = None,
) -> list[str]:
    """Seed `count` indexable crawl snapshots with sections (clears MIN_CRAWLED_PAGES=10)."""
    day = snap_date or date.today()
    root = (base_url or f"https://{client_obj.domain}").rstrip("/")
    urls: list[str] = []
    for i in range(1, count + 1):
        path = f"/services/item-{i}"
        title = f"{client_obj.client_name} Service {i}"
        sections = [
            {
                "level": 1,
                "heading": title,
                "first_paragraph": (
                    f"{client_obj.client_name} provides dependable local service {i} "
                    "with transparent pricing and certified specialists."
                ),
            },
            {
                "level": 2,
                "heading": f"How Service {i} Works",
                "first_paragraph": (
                    f"Our team inspects your property, documents findings clearly, and completes service {i} on schedule."
                ),
            },
        ]
        urls.append(
            seed_crawl_page(
                db,
                client_obj,
                root,
                path,
                day,
                title=title,
                desc=f"Overview of {title}.",
                sections=sections,
                page_type="service",
            )
        )
    db.commit()
    return urls


def seed_ser_kw(
    db: Session,
    client_obj: Client,
    keyword_id: str,
    keyword: str,
    *,
    site_engine_id: str = "1",
    is_tracked: bool = True,
    volume: int | None = 1000,
    current_position: float | None = None,
    ranking_url: str | None = None,
    group_name: str | None = None,
    checked_at: date | None = None,
) -> FactSerKeyword:
    row = FactSerKeyword(
        id=uuid.uuid4(),
        client_id=client_obj.id,
        site_engine_id=site_engine_id,
        keyword_id=keyword_id,
        keyword=keyword,
        is_tracked=is_tracked,
        volume=None if volume is None else Decimal(str(volume)),
        current_position=None if current_position is None else Decimal(str(current_position)),
        ranking_url=ranking_url,
        group_name=group_name,
        checked_at=checked_at,
    )
    db.add(row)
    return row


def seed_ser_metric(
    db: Session,
    client_obj: Client,
    keyword: str,
    *,
    volume: int | None = 500,
    difficulty: int | None = 30,
    cpc: float | None = None,
    intents: list[str] | None = None,
    data_found: bool = True,
    fetched_at: date | None = None,
    source: str = "us",
) -> FactSerKeywordMetric:
    row = FactSerKeywordMetric(
        id=uuid.uuid4(),
        client_id=client_obj.id,
        keyword=keyword,
        source=source,
        volume=None if volume is None else Decimal(str(volume)),
        difficulty=None if difficulty is None else Decimal(str(difficulty)),
        cpc=None if cpc is None else Decimal(str(cpc)),
        intents=intents if intents is not None else ["commercial"],
        data_found=data_found,
        fetched_at=fetched_at or date.today(),
    )
    db.add(row)
    return row


def seed_competitor_kw(
    db: Session,
    client_obj: Client,
    domain: str,
    keyword: str,
    position: float,
    fetched_at: date,
    *,
    volume: int | None = None,
    difficulty: int | None = None,
    ranking_url: str | None = None,
) -> FactSerCompetitorKeyword:
    row = FactSerCompetitorKeyword(
        client_id=client_obj.id,
        competitor_domain=domain,
        keyword=keyword,
        position=Decimal(str(position)),
        volume=None if volume is None else Decimal(str(volume)),
        difficulty=None if difficulty is None else Decimal(str(difficulty)),
        fetched_at=fetched_at,
        ranking_url=ranking_url,
    )
    db.add(row)
    return row


def seed_watch_target_excluded(
    db: Session,
    client_obj: Client,
    target: str,
    *,
    kind: str = "keyword",
    note: str = "Excluded in E2E test",
) -> WatchTarget:
    row = WatchTarget(
        id=uuid.uuid4(),
        client_id=client_obj.id,
        kind=kind,
        item_key=norm_key(target)[:128],
        text=target,
        state="excluded",
        note=note,
        observation={},
    )
    db.add(row)
    db.flush()
    return row


def seed_setup_completion_extras(
    db: Session,
    client_obj: Client,
    *,
    month: str | None = None,
    data_through: date | None = None,
) -> MonthlyRecord | ConsultingReport:
    """Seed activation deliverables (`MonthlyRecord` for execution; profile+report for consulting)."""
    period = month or date.today().strftime("%Y-%m")
    through = data_through or date.today()
    if client_obj.service_mode == "consulting":
        profile = (
            db.query(ConsultingProfile)
            .filter(ConsultingProfile.client_id == client_obj.id)
            .one_or_none()
        )
        if profile is None:
            db.add(
                ConsultingProfile(
                    id=uuid.uuid4(),
                    client_id=client_obj.id,
                    goals="Grow qualified organic demand.",
                    primary_objective="Increase non-brand search visibility.",
                )
            )
        report = (
            db.query(ConsultingReport)
            .filter(
                ConsultingReport.client_id == client_obj.id,
                ConsultingReport.kind == "monthly",
                ConsultingReport.period_month == period,
            )
            .one_or_none()
        )
        if report is None:
            report = ConsultingReport(
                id=uuid.uuid4(),
                client_id=client_obj.id,
                period_month=period,
                kind="monthly",
                title=f"{client_obj.client_name} Monthly Review",
                review_state="published",
            )
            db.add(report)
        db.commit()
        db.refresh(report)
        return report

    existing = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.client_id == client_obj.id, MonthlyRecord.month == period)
        .one_or_none()
    )
    if existing is None:
        existing = MonthlyRecord(
            id=uuid.uuid4(),
            client_id=client_obj.id,
            month=period,
            data_through=through,
            constraint_name="visibility",
            held_since=period,
            confidence="high",
            record={},
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
    return existing


# ── Content Optimizer LLM stub ────────────────────────────────────────────────


def _extract_excerpt_sentence(prompt: str) -> tuple[str, str]:
    marker = "--- THE PAGE'S OWN WORDS (excerpt) ---"
    excerpt = prompt.split(marker, 1)[-1] if marker in prompt else prompt
    excerpt = excerpt.split("\n--- ", 1)[0].strip()
    flat = " ".join(excerpt.split())
    if not flat or flat == "(the page could not be read)":
        return ("Our team provides reliable service.", "Our team provides reliable, expert service.")
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", flat) if len(p.strip()) >= 12]
    before = parts[0] if parts else flat[: min(160, len(flat))]
    if before not in flat:
        before = flat[: min(120, len(flat))]
    after = (
        before[:-1] + " with proven search-aligned clarity."
        if before.endswith((".", "!", "?"))
        else before + " with proven search-aligned clarity."
    )
    if after == before:
        after = before + " (refined)"
    return before, after


def fake_llm_call(depth: str, prompt: str, **_kwargs: Any) -> tuple[str, int, int]:
    """Deterministic offline LLM response passing `content_optimizer.clean()`."""
    if "rewriting ONLY the opening" in prompt:
        payload: dict[str, Any] = {
            "diagnosis": "The current opening does not answer the primary search query directly in sentence one.",
            "options": [
                {
                    "text": (
                        "E2E optimized opening: Get fast, dependable service built around what searchers "
                        "need most, with clear deliverables and upfront expectations."
                    ),
                    "serves": ["target query"],
                    "why": "Answers the core search intent immediately in plain language.",
                },
                {
                    "text": (
                        "E2E alternate opening: Our specialists deliver transparent assessments and "
                        "measurable results tailored to your exact project scope."
                    ),
                    "serves": ["target query"],
                    "why": "Establishes relevance and next steps concisely.",
                },
            ],
        }
    elif "working searched terms" in prompt:
        before, after = _extract_excerpt_sentence(prompt)
        payload = {
            "edits": [
                {
                    "before": before,
                    "after": after,
                    "terms": ["target term"],
                    "why": "Integrates searched terminology naturally into existing page copy.",
                }
            ],
            "left_out": [],
        }
    else:
        payload = {
            "items": [
                {
                    "question": "How does this service work from initial inspection to completion?",
                    "answer": "Our team inspects the issue, documents findings clearly, and completes the work on schedule.",
                    "from_search": "target query",
                },
                {
                    "question": "What should customers expect regarding pricing and scheduling?",
                    "answer": "We provide transparent pricing and clear timelines before any work begins.",
                    "from_search": "target query",
                },
            ]
        }
    return json.dumps(payload), 1200, 300


@pytest.fixture
def stub_optimizer_llm(monkeypatch):
    """Enable Content Optimizer locally and stub `app.schema_tools.llm.call`."""
    from app.schema_tools import llm

    monkeypatch.setenv("ANTHROPIC_API_KEY", "e2e-stub-key")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "e2e-stub-key")
    monkeypatch.setattr(llm, "call", fake_llm_call)
    return fake_llm_call
