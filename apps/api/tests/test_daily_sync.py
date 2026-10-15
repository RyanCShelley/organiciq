import pytest
from datetime import date, datetime, timezone

from app.ingestion.dataforseo.keyword_metrics import KEYWORD_METRICS_INTERVAL_DAYS
from app.models.client import Client
from app.models.integration import Integration, IntegrationProvider
from app.models.job import SyncJob
from app.models.scheduler import SchedulerCheckpoint
from app.services import daily_sync
from app.services.daily_sync import DAILY_CHECKPOINT


def test_lookback_window_three_days():
    start, end = daily_sync._lookback_window(3)
    assert end == date.today()
    assert (end - start).days == 2


def test_maybe_run_daily_sync_enqueues_mapped_sources(db, client_a: Client, monkeypatch):
    settings = daily_sync.get_settings()
    monkeypatch.setattr(settings, "daily_sync_enabled", True)
    monkeypatch.setattr(settings, "daily_sync_hour_utc", 0)
    monkeypatch.setattr(settings, "daily_sync_lookback_days", 3)

    for provider, property_id in (
        (IntegrationProvider.GSC, "sc-domain:example.com"),
        (IntegrationProvider.GA4, "properties/123"),
    ):
        row = (
            db.query(Integration)
            .filter(Integration.client_id == client_a.id, Integration.provider == provider)
            .one()
        )
        row.external_property_id = property_id
    db.commit()

    fixed_now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is None else fixed_now.astimezone(tz)

    monkeypatch.setattr(daily_sync, "datetime", _FixedDateTime)

    assert daily_sync.maybe_run_daily_sync(db) is True
    checkpoint = db.get(SchedulerCheckpoint, DAILY_CHECKPOINT)
    assert checkpoint is not None
    assert checkpoint.last_run_date == fixed_now.date()

    jobs = db.query(SyncJob).filter(SyncJob.client_id == client_a.id).all()
    sources = {j.source for j in jobs}
    assert "gsc_pages" in sources
    assert "gsc_queries" in sources
    assert "ga4" in sources

    assert daily_sync.maybe_run_daily_sync(db) is False


@pytest.fixture(autouse=True)
def _dataforseo_configured(monkeypatch):
    """Keyword pricing and competitor reads are DataForSEO's, and are not queued without it."""
    from app.integrations import dataforseo

    monkeypatch.setattr(
        dataforseo, "load_config", lambda: dataforseo.DataForSeoConfig(login="l", password="p")
    )


def _track(db, client_id, keyword: str) -> None:
    from app.models.seranking import FactSerKeyword

    db.add(
        FactSerKeyword(
            client_id=client_id,
            keyword=keyword,
            site_engine_id="1",
            keyword_id=keyword,
            current_position=0,
        )
    )
    db.commit()


def _price(db, client_id, keyword: str, fetched_at: date) -> None:
    from app.models.seranking import FactSerKeywordMetric

    db.add(
        FactSerKeywordMetric(
            client_id=client_id,
            keyword=keyword,
            source="us",
            volume=100,
            difficulty=20,
            fetched_at=fetched_at,
        )
    )
    db.commit()


def test_keyword_metrics_due_when_nothing_priced(db, client_a: Client):
    _track(db, client_a.id, "managed it services")
    stats = daily_sync.enqueue_due_keyword_metrics(db)
    assert stats["due"] == 1
    assert stats["enqueued"] == 1
    job = (
        db.query(SyncJob)
        .filter(SyncJob.source == "dataforseo_keyword_metrics")
        .one()
    )
    assert job.client_id == client_a.id


def test_keyword_metrics_not_due_when_priced_this_month(db, client_a: Client):
    _track(db, client_a.id, "managed it services")
    _price(db, client_a.id, "managed it services", date.today())
    assert daily_sync.enqueue_due_keyword_metrics(db)["due"] == 0


def test_keyword_metrics_due_again_when_the_pull_is_old(db, client_a: Client):
    from datetime import timedelta

    _track(db, client_a.id, "managed it services")
    _price(
        db,
        client_a.id,
        "managed it services",
        date.today() - timedelta(days=KEYWORD_METRICS_INTERVAL_DAYS),
    )
    assert daily_sync.enqueue_due_keyword_metrics(db)["due"] == 1


def test_keyword_metrics_due_for_a_term_added_since(db, client_a: Client):
    """A new keyword is unpriced however fresh the last pull was."""
    _track(db, client_a.id, "managed it services")
    _price(db, client_a.id, "managed it services", date.today())
    _track(db, client_a.id, "cybersecurity services")
    assert daily_sync.enqueue_due_keyword_metrics(db)["due"] == 1


def test_keyword_metrics_skips_a_client_tracking_nothing(db, client_a: Client):
    assert daily_sync.enqueue_due_keyword_metrics(db)["due"] == 0


def test_keyword_metrics_not_due_when_only_the_case_differs(db, client_a: Client):
    """Raw-string comparison kept a client 'due' forever and re-bought its list daily."""
    _track(db, client_a.id, "  Managed IT Services ")
    _price(db, client_a.id, "managed it services", date.today())
    assert daily_sync.enqueue_due_keyword_metrics(db)["due"] == 0
