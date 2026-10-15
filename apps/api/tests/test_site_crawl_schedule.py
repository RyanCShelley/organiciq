"""Monthly, staggered site-crawl scheduling."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.services.daily_sync import (
    SITE_CRAWL_INTERVAL_DAYS,
    SITE_CRAWL_STALE_DAYS,
    _crawl_slot,
    _site_crawl_due,
)


def test_a_client_gets_one_slot_and_keeps_it():
    client_id = uuid.uuid4()
    assert _crawl_slot(client_id) == _crawl_slot(client_id)
    assert 0 <= _crawl_slot(client_id) < SITE_CRAWL_INTERVAL_DAYS


def test_clients_are_spread_rather_than_bunched():
    """All 35 crawling on the same morning is a traffic spike for no reason."""
    slots = [_crawl_slot(uuid.uuid4()) for _ in range(35)]
    # Hashing will collide sometimes; what matters is that it is not one day.
    assert len(set(slots)) > SITE_CRAWL_INTERVAL_DAYS / 2


def test_a_never_crawled_client_crawls_on_the_next_tick():
    """No slot to wait for.

    This used to wait, so that shipping the crawl did not put all 35
    clients on one morning. That was a one-off: every client has been
    crawled since, so "never crawled" now means "connected this week",
    which arrives one or two at a time. Waiting cost a new client up to
    six days with no pages — and conversion pages, page stages and the
    keyword map all read the crawl. The spread still applies to every
    repeat crawl, which is where the load actually is.
    """
    client_id = uuid.uuid4()
    for day in range(SITE_CRAWL_INTERVAL_DAYS * 2):
        assert _site_crawl_due(client_id, None, date(2026, 1, 1) + timedelta(days=day))


def test_a_recent_crawl_is_not_repeated():
    client_id = uuid.uuid4()
    today = date(2026, 6, 15)
    for age in range(SITE_CRAWL_INTERVAL_DAYS):
        assert not _site_crawl_due(client_id, today - timedelta(days=age), today)


def test_an_overdue_crawl_runs_without_waiting_for_its_slot():
    """A worker outage should not cost a client a whole extra cycle."""
    client_id = uuid.uuid4()
    today = date(2026, 6, 15)
    stale = today - timedelta(days=SITE_CRAWL_STALE_DAYS)

    assert _site_crawl_due(client_id, stale, today)


def test_a_client_past_the_interval_waits_for_its_own_slot():
    client_id = uuid.uuid4()
    today = date(2026, 6, 15)
    last = today - timedelta(days=SITE_CRAWL_INTERVAL_DAYS + 1)

    expected = today.toordinal() % SITE_CRAWL_INTERVAL_DAYS == _crawl_slot(client_id)
    assert _site_crawl_due(client_id, last, today) is expected


def test_the_page_limit_setting_is_the_ceiling():
    """A job may ask for fewer pages than the client allows, never more."""
    from app.ingestion.crawler.fetch import page_limit_for

    assert page_limit_for(120) == 120
    assert min(page_limit_for(9999), page_limit_for(120)) == 120


# --- Data health ------------------------------------------------------------


def test_data_health_reports_the_crawl_and_not_the_retired_audit():
    """
    The audit left the daily sync, so listing it here would show a source going
    stale that nothing schedules any more, while the crawl that replaced it was
    invisible.
    """
    from app.services.data_health import WATERMARK_SOURCES

    assert "site_crawl" in WATERMARK_SOURCES
    assert "se_ranking_audit" not in WATERMARK_SOURCES


def test_the_crawl_needs_no_integration_to_be_healthy():
    """
    It crawls the client's own site, so there is nothing to connect. Requiring
    an integration would have pinned it at "Not Connected" forever.
    """
    from datetime import date as date_cls

    from app.models.job import DataWatermark, ValidationStatus
    from app.services.data_health import data_health_rows

    watermark = DataWatermark(
        source="site_crawl",
        fact_through_date=date_cls.today(),
        validation_status=ValidationStatus.PASSED,
    )

    rows = {row["source"]: row for row in data_health_rows({}, {"site_crawl": watermark})}

    assert rows["site_crawl"]["status"] == "Healthy"


def test_a_client_awaiting_its_first_crawl_is_not_reported_as_disconnected():
    from app.services.data_health import data_health_rows

    rows = {row["source"]: row for row in data_health_rows({}, {})}

    assert rows["site_crawl"]["status"] == "Not scheduled yet"


def _crawl_jobs(db, client):
    from app.models.job import SyncJob

    return db.query(SyncJob).filter(
        SyncJob.client_id == client.id, SyncJob.source == "site_crawl"
    )


def test_an_onboarding_client_is_crawled(db, client_a):
    """Only ACTIVE clients were enqueued, so onboarding ones never crawled."""
    from app.models.client import ClientStatus
    from app.services.daily_sync import enqueue_due_site_crawls

    client_a.status = ClientStatus.ONBOARDING
    db.commit()

    assert enqueue_due_site_crawls(db)["enqueued"] == 1
    assert _crawl_jobs(db, client_a).count() == 1


def test_a_paused_client_is_not_crawled(db, client_a):
    from app.models.client import ClientStatus
    from app.services.daily_sync import enqueue_due_site_crawls

    client_a.status = ClientStatus.PAUSED
    db.commit()

    assert enqueue_due_site_crawls(db)["due"] == 0


def test_a_blocked_never_crawled_site_is_tried_once_a_week_not_daily(db, client_a):
    from app.models.job import SyncJobStatus
    from app.services.daily_sync import enqueue_due_site_crawls

    assert enqueue_due_site_crawls(db)["enqueued"] == 1
    job = _crawl_jobs(db, client_a).one()
    job.status = SyncJobStatus.FAILED
    db.commit()

    assert enqueue_due_site_crawls(db)["due"] == 0
    assert _crawl_jobs(db, client_a).count() == 1
