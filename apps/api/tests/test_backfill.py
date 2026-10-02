"""Queueing a long historical sync."""

from __future__ import annotations

from datetime import date

import pytest

from app.backfill import MAX_MONTHS, backfill_window

TODAY = date(2026, 10, 1)


def test_the_window_ends_before_today_because_search_console_lags():
    start, end = backfill_window("gsc_pages", 16, TODAY)

    assert end == date(2026, 9, 28)
    assert start < end


def test_sixteen_months_is_about_a_year_and_a_third():
    start, end = backfill_window("gsc_pages", 16, TODAY)

    assert (end - start).days + 1 == 487


@pytest.mark.parametrize("asked", [24, 36, 120])
def test_search_console_is_capped_at_what_it_serves(asked):
    """Asking for more returns nothing extra, so the window says what it means."""
    capped_start, _ = backfill_window("gsc_pages", asked, TODAY)
    max_start, _ = backfill_window("gsc_pages", MAX_MONTHS["gsc_pages"], TODAY)

    assert capped_start == max_start


def test_ga4_is_not_capped_because_the_property_decides():
    start_16, _ = backfill_window("ga4", 16, TODAY)
    start_36, _ = backfill_window("ga4", 36, TODAY)

    assert start_36 < start_16


def test_a_short_window_is_honoured():
    start, end = backfill_window("gsc_pages", 3, TODAY)

    assert (end - start).days + 1 == 91


def test_a_crawl_takes_a_single_day_window():
    """A crawl reads the site as it is now; there is no history to ask for."""
    start, end = backfill_window("site_crawl", 16, TODAY)

    assert start == end == TODAY


def test_the_crawl_window_ignores_the_months_asked_for():
    assert backfill_window("site_crawl", 1, TODAY) == backfill_window("site_crawl", 36, TODAY)
