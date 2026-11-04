from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.settings import get_settings
from app.integrations import bing
from app.models.bing_stats import FactBingQueryStat
from app.models.client import Client
from app.models.client_bing_site import ClientBingSite
from app.models.job import DataWatermark, SyncJob, SyncJobStatus
from app.services import bing_sync, daily_sync
from app.services.jobs import process_job


@pytest.fixture(autouse=True)
def bing_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "bing_webmaster_api_key", "test-key")


def _site(db, client: Client) -> None:
    db.add(ClientBingSite(client_id=client.id, site_url="https://zz.example/", status="connected"))
    db.commit()


def _jobs(db, client: Client) -> list[SyncJob]:
    return db.query(SyncJob).filter(SyncJob.client_id == client.id, SyncJob.source == "bing_query_stats").all()


def test_a_client_with_a_bing_site_is_queued_once(db, client_a: Client):
    _site(db, client_a)
    assert daily_sync.enqueue_due_bing_syncs(db)["enqueued"] == 1
    assert len(_jobs(db, client_a)) == 1
    # Already queued: the next cycle does not stack a second one.
    assert daily_sync.enqueue_due_bing_syncs(db)["enqueued"] == 0


def test_a_client_with_no_bing_site_or_no_key_is_not_queued(db, client_a: Client, monkeypatch):
    assert daily_sync.enqueue_due_bing_syncs(db)["due"] == 0
    _site(db, client_a)
    monkeypatch.setattr(get_settings(), "bing_webmaster_api_key", "")
    assert daily_sync.enqueue_due_bing_syncs(db)["due"] == 0


def test_a_recent_success_is_not_pulled_again_but_an_old_one_is(db, client_a: Client):
    _site(db, client_a)
    mark = DataWatermark(
        client_id=client_a.id,
        source=bing_sync.BING_SOURCE,
        fact_through_date=date.today(),
        last_successful_sync_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db.add(mark)
    db.commit()
    assert daily_sync.enqueue_due_bing_syncs(db)["due"] == 0
    mark.last_successful_sync_at = datetime.now(timezone.utc) - timedelta(days=8)
    db.commit()
    assert daily_sync.enqueue_due_bing_syncs(db)["enqueued"] == 1


def test_the_job_stores_the_weeks_and_moves_the_watermark(db, client_a: Client, monkeypatch):
    _site(db, client_a)
    rows = [
        {"week_start": date(2026, 10, 18), "query": "Natural sunscreen", "impressions": 40, "clicks": 3,
         "avg_impression_position": 5.0, "avg_click_position": 4.0},
    ]
    monkeypatch.setattr(bing, "query_stats", lambda key, site: rows)
    daily_sync.enqueue_due_bing_syncs(db)
    job = _jobs(db, client_a)[0]
    done = process_job(db, job)
    assert done.status == SyncJobStatus.SUCCESSFUL
    assert db.query(FactBingQueryStat).filter(FactBingQueryStat.client_id == client_a.id).count() == 1
    mark = db.query(DataWatermark).filter(DataWatermark.client_id == client_a.id, DataWatermark.source == "bing_query_stats").one()
    assert mark.fact_through_date == date(2026, 10, 18)


def test_a_failed_pull_is_recorded_and_retried_later_not_daily(db, client_a: Client, monkeypatch):
    _site(db, client_a)

    def boom(key, site):
        raise RuntimeError("Bing said no")

    monkeypatch.setattr(bing, "query_stats", boom)
    daily_sync.enqueue_due_bing_syncs(db)
    done = process_job(db, _jobs(db, client_a)[0])
    assert done.status == SyncJobStatus.FAILED
    assert "Bing said no" in done.error_message
    assert daily_sync.enqueue_due_bing_syncs(db)["due"] == 0
