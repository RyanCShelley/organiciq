"""The window the daily sync asks each source for.

Every client's Search Console data stopped on 24 September 2026 and nothing
noticed for fifteen days. The daily sync asked every source for the last three
days ending today; Search Console finalises a day two to three days late, so
that window sat entirely inside the lag, came back empty for every client every
day, was recorded as success, and pushed the watermark to today. The next run
asked for the same empty window. Nothing could ever catch up.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from app.models.gsc import FactGscPage
from app.services.daily_sync import (
    MAX_CATCHUP_DAYS,
    RESTATEMENT_OVERLAP_DAYS,
    SOURCE_LAG_DAYS,
    _window_for_source,
)

TODAY = date.today()


def _fact(client_id, when: date) -> FactGscPage:
    return FactGscPage(
        id=uuid4(),
        client_id=client_id,
        date=when,
        raw_url="https://x/p",
        normalized_url="https://x/p",
        impressions=10,
        clicks=1,
        ctr=0.1,
        average_position=5,
    )


def test_the_window_stops_short_of_search_consoles_lag(db, client_a):
    """The whole bug in one line: a window ending today has nothing in it."""
    _start, end = _window_for_source(db, client_a.id, "gsc_pages", 3)
    assert end == TODAY - timedelta(days=SOURCE_LAG_DAYS["gsc_pages"])
    assert end < TODAY


def test_the_old_window_would_have_been_entirely_inside_the_lag():
    """Three days ending today, against a three-day lag. Not one requested
    day could have returned anything."""
    old_start, old_end = TODAY - timedelta(days=2), TODAY
    first_day_with_data = TODAY - timedelta(days=SOURCE_LAG_DAYS["gsc_pages"])
    assert old_start > first_day_with_data
    assert old_end > first_day_with_data


def test_a_client_that_fell_behind_catches_up(db, client_a):
    """SMA's facts stopped on 24 September while the job kept asking for the
    last three days. The window starts where the data stops."""
    stopped = TODAY - timedelta(days=15)
    db.add(_fact(client_a.id, stopped))
    db.commit()

    start, _end = _window_for_source(db, client_a.id, "gsc_pages", 3)
    assert start <= stopped
    assert start == stopped - timedelta(days=RESTATEMENT_OVERLAP_DAYS)


def test_recent_days_are_asked_for_again(db, client_a):
    """Search Console restates recent days, so the newest are refetched
    rather than trusted."""
    yesterday = TODAY - timedelta(days=4)
    db.add(_fact(client_a.id, yesterday))
    db.commit()

    start, _ = _window_for_source(db, client_a.id, "gsc_pages", 3)
    assert start < yesterday


def test_a_client_years_behind_is_not_asked_for_everything(db, client_a):
    """A catch-up still happens over several runs rather than one enormous
    request."""
    db.add(_fact(client_a.id, TODAY - timedelta(days=900)))
    db.commit()

    start, end = _window_for_source(db, client_a.id, "gsc_pages", 3)
    assert (end - start).days <= MAX_CATCHUP_DAYS


def test_a_client_with_no_facts_gets_the_plain_lookback(db, client_a):
    """Nothing to catch up to, so it asks for the ordinary window — ending
    where the data can exist."""
    start, end = _window_for_source(db, client_a.id, "gsc_pages", 3)
    assert (end - start).days == 2
    assert end == TODAY - timedelta(days=SOURCE_LAG_DAYS["gsc_pages"])


def test_ga4_is_only_a_day_behind(db, client_a):
    """GA4 keeps revising the current day, but yesterday is stable. Giving it
    Search Console's lag would throw away two usable days."""
    _start, end = _window_for_source(db, client_a.id, "ga4", 3)
    assert end == TODAY - timedelta(days=1)


def test_a_source_with_no_declared_lag_still_ends_today(db, client_a):
    """The site crawl is of the site as it is now."""
    _start, end = _window_for_source(db, client_a.id, "site_crawl", 1)
    assert end == TODAY


def test_the_window_never_runs_backwards(db, client_a):
    db.add(_fact(client_a.id, TODAY + timedelta(days=5)))
    db.commit()
    start, end = _window_for_source(db, client_a.id, "gsc_pages", 3)
    assert start <= end
