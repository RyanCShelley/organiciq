from datetime import date, datetime, timezone

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
