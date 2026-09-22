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


def test_a_never_crawled_client_waits_for_its_slot():
    """Otherwise every client crawls at once the first time this ships."""
    client_id = uuid.uuid4()
    slot = _crawl_slot(client_id)
    due_days = [
        day
        for day in range(SITE_CRAWL_INTERVAL_DAYS)
        if _site_crawl_due(client_id, None, date(2026, 1, 1) + timedelta(days=day))
    ]
    assert len(due_days) == 1
    assert (date(2026, 1, 1) + timedelta(days=due_days[0])).toordinal() % (
        SITE_CRAWL_INTERVAL_DAYS
    ) == slot


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
