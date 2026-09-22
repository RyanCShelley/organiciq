from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import date, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Always isolate tests from the local/dev database.
os.environ["DATABASE_URL"] = "postgresql+psycopg://ryanshelley@localhost:5432/organiciq_test"
os.environ["AUTH_SECRET"] = "test-auth-secret"
os.environ["SMA_ADMIN_EMAILS"] = "admin@smamarketing.net"

from app.core.db import Base, get_db  # noqa: E402
from app.core.settings import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402, F401 — register all models on Base.metadata
    Annotation,
    FactGa4Event,
    FactGa4Traffic,
    FactGscDaily,
    FactGscPage,
    FactCrawlPageIssue,
    FactCrawlPageSnapshot,
    Decision,
    DecisionThreshold,
    FactGscQueryPage,
    FactSerCompetitor,
    FactSerKeyword,
    FactSerRanking,
    FactSerAiCheck,
    FactSerAiPrompt,
    SchedulerCheckpoint,
    StagingGa4Event,
    StagingGa4Traffic,
    StagingGscDaily,
    StagingGscPage,
    StagingGscQueryPage,
    StagingSerAuditIssue,
    StagingSerAuditPage,
    StagingSerCompetitor,
    StagingSerKeyword,
    StagingSerPosition,
    StagingSerAiCheck,
    StagingSerAiPrompt,
)
from app.models.client import Client, ClientStatus, Tier  # noqa: E402
from app.models.integration import ConnectionStatus, Integration, IntegrationProvider  # noqa: E402
from app.models.user import User, UserClient, UserRole  # noqa: E402

get_settings.cache_clear()
settings = get_settings()


def _ensure_test_database() -> str:
    url = settings.database_url
    if "organiciq_test" not in url:
        return url

    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'organiciq_test'")
        ).scalar()
        if not exists:
            conn.execute(text("CREATE DATABASE organiciq_test"))
    engine.dispose()
    return url


@pytest.fixture(scope="session")
def engine():
    url = _ensure_test_database()
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


@pytest.fixture
def db(engine) -> Generator[Session, None, None]:
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield session
    session.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def tier(db: Session) -> Tier:
    row = Tier(
        id=uuid.uuid4(),
        tier_name=f"Tier-{uuid.uuid4().hex[:8]}",
        tracked_keyword_limit=100,
        tracked_prompt_limit=50,
        content_allowance=3,
        update_allowance=3,
        growth_action_allowance=1,
        watchlist_cadence="monthly",
        conversion_limit=3,
        reporting_level="launch",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_client(db: Session, tier: Tier, name: str) -> Client:
    c = Client(
        id=uuid.uuid4(),
        client_name=name,
        slug=name.lower().replace(" ", "-"),
        domain=f"{name.lower().replace(' ', '')}.example",
        tier_id=tier.id,
        status=ClientStatus.ACTIVE,
        timezone="America/New_York",
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


@pytest.fixture
def client_a(db: Session, tier: Tier) -> Client:
    return _make_client(db, tier, "Client A")


@pytest.fixture
def client_b(db: Session, tier: Tier) -> Client:
    return _make_client(db, tier, "Client B")


@pytest.fixture
def admin_user(db: Session) -> User:
    user = User(
        id=uuid.uuid4(),
        email="admin@smamarketing.net",
        name="Admin",
        google_sub="admin-sub",
        role=UserRole.SMA_ADMIN,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def team_user(db: Session, client_a: Client) -> User:
    user = User(
        id=uuid.uuid4(),
        email="team@smamarketing.net",
        name="Team",
        google_sub="team-sub",
        role=UserRole.SMA_TEAM,
    )
    db.add(user)
    db.flush()
    db.add(UserClient(user_id=user.id, client_id=client_a.id, role=UserRole.SMA_TEAM))
    db.commit()
    db.refresh(user)
    return user


def auth_header(email: str) -> dict[str, str]:
    token = jwt.encode(
        {"email": email, "sub": email},
        settings.auth_secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def client_header(client_id: uuid.UUID, email: str) -> dict[str, str]:
    return {
        **auth_header(email),
        "X-OrganicIQ-Client-Id": str(client_id),
    }


def date_window(days: int = 14) -> tuple[date, date]:
    end = date.today()
    start = end - timedelta(days=days - 1)
    return start, end


def seed_required_sources(
    db: Session,
    client_id: uuid.UUID,
    through: date,
    *,
    skip: tuple[str, ...] = (),
) -> None:
    """
    Make every Decision Engine source report ready.

    The engine refuses to run unless all four are present, so a test about one
    lever still has to satisfy the other three. `skip` leaves a source out, for
    tests that assert the refusal itself.
    """
    import uuid as _uuid
    from decimal import Decimal

    from app.models.config import OrganicChannel
    from app.models.crawl import FactCrawlPageSnapshot
    from app.services.lever_engine import active_crawl_source
    from app.models.ga4 import FactGa4Traffic
    from app.models.gsc import FactGscPage
    from app.models.job import DataWatermark, ValidationStatus

    def _watermark(source: str) -> None:
        row = (
            db.query(DataWatermark)
            .filter(DataWatermark.client_id == client_id, DataWatermark.source == source)
            .one_or_none()
        )
        if row is None:
            db.add(
                DataWatermark(
                    id=_uuid.uuid4(),
                    client_id=client_id,
                    source=source,
                    fact_through_date=through,
                    validation_status=ValidationStatus.PASSED,
                )
            )
        else:
            row.fact_through_date = through
            row.validation_status = ValidationStatus.PASSED

    def _has(model) -> bool:
        return db.query(model).filter(model.client_id == client_id).first() is not None

    if "search_console" not in skip:
        _watermark("gsc_pages")
        if not _has(FactGscPage):
            db.add(
                FactGscPage(
                    id=_uuid.uuid4(),
                    client_id=client_id,
                    date=through,
                    raw_url="https://example.com/baseline",
                    normalized_url="https://example.com/baseline",
                    country="",
                    device="",
                    impressions=Decimal("10"),
                    clicks=Decimal("1"),
                    ctr=Decimal("0.1"),
                    average_position=Decimal("10"),
                )
            )

    if "analytics" not in skip:
        _watermark("ga4")
        if not _has(FactGa4Traffic):
            db.add(
                FactGa4Traffic(
                    id=_uuid.uuid4(),
                    client_id=client_id,
                    date=through,
                    channel=OrganicChannel.ORGANIC_SEARCH,
                    raw_url="https://example.com/baseline",
                    normalized_url="https://example.com/baseline",
                    sessions=Decimal("10"),
                    active_users=Decimal("8"),
                    views=Decimal("12"),
                    engaged_sessions=Decimal("6"),
                )
            )

    if "crawl_audit" not in skip and not _has(FactCrawlPageSnapshot):
        db.add(
            FactCrawlPageSnapshot(
                id=_uuid.uuid4(),
                client_id=client_id,
                source=active_crawl_source(),
                snapshot_date=through,
                raw_url="https://example.com/baseline",
                normalized_url="https://example.com/baseline",
                indexable=True,
                status_code=200,
                inbound_internal_links=3,
                word_count=600,
                in_sitemap=True,
            )
        )

    if "ai_visibility" not in skip:
        _watermark("se_ranking_ai")

    db.commit()
