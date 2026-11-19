"""Isolated E2E test harness for OrganicIQ Phase 2 (`organiciq_test_e2e`).

Shadows root `tests/conftest.py:engine` so custom `TEST_DATABASE_URL` databases
such as `organiciq_test_e2e` are auto-created and torn down cleanly without
touching `organiciq_test`, `organiciq_test_m2`, or `organiciq_prod_slim`.

Opaque-box rule: imports ONLY stable pre-existing ORM models, core DB/test
helpers, and `google_updates` for network isolation — never M1/M2 internals.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal
from typing import Iterable

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.db import Base
from app.models.client import Client, ClientStatus, Tier
from app.models.crawl import (
    CRAWL_SOURCE_FIRST_PARTY,
    FactCrawlInternalLink,
    FactCrawlPageIssue,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from app.models.bing_stats import FactBingQueryStat
from app.models.google_update import GoogleSearchUpdate
from app.models.gsc import FactGscQueryPage
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider
from app.models.llm_visibility import LlmResponse, LlmRun
from app.models.seranking import FactSerCompetitorKeyword, FactSerRanking
from app.models.site_health import SiteHealthSnapshot
from app.models.user import User, UserClient, UserRole
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services import google_updates
from tests.conftest import auth_header, client_header, settings


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
    """Shadow root `tests/conftest.py:engine` for isolated `organiciq_test_e2e` runs."""
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
def _no_google_updates_network(monkeypatch):
    """Prevent GET /v2/search-visibility from hitting Google's live status feed."""

    def _refuse(*_args, **_kwargs):
        raise RuntimeError("no external network calls in E2E tests")

    monkeypatch.setattr(google_updates.httpx, "get", _refuse)


# ── Auth & HTTP header helpers ────────────────────────────────────────────────


def admin_headers(client_obj: Client) -> dict[str, str]:
    return client_header(client_obj.id, "admin@smamarketing.com")


def api_headers(client_id: uuid.UUID | None = None, email: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if email is not None:
        headers.update(auth_header(email))
    if client_id is not None:
        headers["X-OrganicIQ-Client-Id"] = str(client_id)
    return headers


def make_client(
    db: Session,
    tier: Tier,
    name: str,
    *,
    domain: str | None = None,
    brand_aliases: list[str] | None = None,
) -> Client:
    slug_base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "client"
    c = Client(
        id=uuid.uuid4(),
        client_name=name,
        slug=f"{slug_base}-{uuid.uuid4().hex[:6]}",
        domain=domain or f"{slug_base.replace('-', '')}.example",
        tier_id=tier.id,
        status=ClientStatus.ACTIVE,
        timezone="America/New_York",
        brand_aliases=brand_aliases if brand_aliases is not None else [],
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


def make_user(
    db: Session,
    *,
    email: str,
    role: UserRole,
    assign_clients: Iterable[Client] = (),
) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email.lower(),
        name=email.split("@", 1)[0],
        google_sub=f"sub-{uuid.uuid4().hex[:10]}",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    for c in assign_clients:
        db.add(UserClient(user_id=user.id, client_id=c.id, role=role))
    db.commit()
    db.refresh(user)
    return user


# ── Stable ORM seeding helpers ────────────────────────────────────────────────


def norm_key(value: str) -> str:
    return " ".join(value.strip().lower().split())


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
) -> str:
    url = f"{base_url.rstrip('/')}{path}"
    db.add(
        FactCrawlPageSnapshot(
            client_id=client_obj.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
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
        )
    )
    return url


def seed_schema(
    db: Session,
    client_obj: Client,
    base_url: str,
    path: str,
    snap_date: date,
    *,
    kind: str = "Product",
    syntax: str = "json_ld",
    raw_text: str | None = None,
    parse_error: str | None = None,
) -> None:
    url = f"{base_url.rstrip('/')}{path}"
    db.add(
        FactCrawlPageSchema(
            client_id=client_obj.id,
            snapshot_date=snap_date,
            normalized_url=url,
            syntax=syntax,
            schema_type=kind,
            raw_text=raw_text or f'{{"@type":"{kind}"}}',
            parse_error=parse_error,
        )
    )


def seed_internal_link(
    db: Session,
    client_obj: Client,
    snap_date: date,
    from_url: str,
    to_url: str,
    *,
    in_content: bool = True,
    is_template: bool = False,
    occurrences: int = 1,
) -> None:
    db.add(
        FactCrawlInternalLink(
            client_id=client_obj.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=snap_date,
            from_url=from_url,
            to_url=to_url,
            in_content=in_content,
            is_template=is_template,
            occurrences=occurrences,
        )
    )


def seed_crawl_issue(
    db: Session,
    client_obj: Client,
    snap_date: date,
    issue_code: str,
    *,
    normalized_url: str | None = None,
    raw: dict | None = None,
    severity: str | None = None,
) -> None:
    db.add(
        FactCrawlPageIssue(
            client_id=client_obj.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=snap_date,
            issue_code=issue_code,
            normalized_url=normalized_url,
            raw=raw if raw is not None else {},
            severity=severity,
        )
    )


def seed_gsc(
    db: Session,
    client_obj: Client,
    day: date,
    query: str,
    impressions: int,
    position: float,
    *,
    clicks: int = 1,
    url: str = "https://shop.example/page",
    country: str = "usa",
    device: str = "DESKTOP",
) -> None:
    ctr = Decimal(clicks) / Decimal(impressions) if impressions > 0 else Decimal(0)
    db.add(
        FactGscQueryPage(
            client_id=client_obj.id,
            date=day,
            query=query,
            raw_url=url,
            normalized_url=url,
            country=country,
            device=device,
            impressions=Decimal(impressions),
            clicks=Decimal(clicks),
            ctr=ctr,
            average_position=Decimal(str(position)),
        )
    )


def seed_bing(
    db: Session,
    client_obj: Client,
    week_start: date,
    query: str,
    impressions: int,
    *,
    clicks: int = 1,
    avg_pos: Decimal | float | None = Decimal("10.0"),
) -> None:
    pos_val = None if avg_pos is None else Decimal(str(avg_pos))
    db.add(
        FactBingQueryStat(
            client_id=client_obj.id,
            week_start=week_start,
            query=query,
            query_key=norm_key(query),
            impressions=impressions,
            clicks=clicks,
            avg_impression_position=pos_val,
        )
    )


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
    paired_ai_prompt: str | None = None,
    notes: str | None = None,
) -> WatchlistKeyword:
    kw = WatchlistKeyword(
        client_id=client_obj.id,
        bucket_id=bucket.id,
        keyword=keyword,
        keyword_key=norm_key(keyword),
        volume=volume,
        paired_ai_prompt=paired_ai_prompt,
        notes=notes,
    )
    db.add(kw)
    db.flush()
    return kw


def seed_snapshot(
    db: Session,
    client_obj: Client,
    month: str,
    crawl_date: date,
    payload: dict,
) -> SiteHealthSnapshot:
    snap = SiteHealthSnapshot(
        client_id=client_obj.id,
        month=month,
        crawl_date=crawl_date,
        payload=payload,
    )
    db.add(snap)
    db.flush()
    return snap


def seed_llm_run(
    db: Session,
    client_obj: Client,
    responses: list[dict],
) -> LlmRun:
    run = LlmRun(
        client_id=client_obj.id,
        status="completed",
        platforms=sorted({r["platform"] for r in responses}),
    )
    db.add(run)
    db.flush()
    for r in responses:
        db.add(
            LlmResponse(
                run_id=run.id,
                client_id=client_obj.id,
                query_text=r["query_text"],
                platform=r["platform"],
                visibility_type=r.get("visibility_type", "Mentioned"),
                brand_mentioned=r.get("brand_mentioned", False),
                url_cited=r.get("url_cited", False),
                full_response=r.get("full_response", "Generic response text."),
            )
        )
    db.flush()
    return run


def seed_google_update(
    db: Session,
    *,
    update_id: str,
    title: str,
    begin: date,
    end: date | None = None,
) -> GoogleSearchUpdate:
    upd = GoogleSearchUpdate(
        id=update_id,
        title=title,
        begin=begin,
        end=end,
    )
    db.add(upd)
    db.flush()
    return upd


def seed_ser_ranking(
    db: Session,
    client_obj: Client,
    day: date,
    keyword_id: str,
    keyword: str,
    position: float,
    *,
    volume: int = 1000,
    ranking_url: str = "https://shop.example/page",
) -> None:
    db.add(
        FactSerRanking(
            client_id=client_obj.id,
            date=day,
            site_engine_id="1",
            keyword_id=keyword_id,
            keyword=keyword,
            position=Decimal(str(position)),
            volume=Decimal(volume),
            ranking_url=ranking_url,
        )
    )


def seed_competitor_kw(
    db: Session,
    client_obj: Client,
    domain: str,
    keyword: str,
    position: float,
    fetched_at: date,
    *,
    ranking_url: str | None = None,
) -> None:
    db.add(
        FactSerCompetitorKeyword(
            client_id=client_obj.id,
            competitor_domain=domain,
            keyword=keyword,
            position=Decimal(str(position)),
            fetched_at=fetched_at,
            ranking_url=ranking_url,
        )
    )
